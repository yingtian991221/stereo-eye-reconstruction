// Stage profiler only. Reuses the unchanged CUDA implementation and kernels.
#define main original_pirate_bench_main
#include "pirate_bench.cu"
#undef main

#include <numeric>

namespace stage_profile {
using Clock = std::chrono::steady_clock;
double milliseconds(Clock::time_point a, Clock::time_point b) {
    return std::chrono::duration<double, std::milli>(b - a).count();
}
double elapsed(const Event &a, const Event &b) {
    float value;
    CK(cudaEventElapsedTime(&value, a.e, b.e));
    return value;
}

// Preallocated once per frame. No event creation or inter-stage synchronization
// in the timed path. Consecutive event boundaries partition reconstruction.
struct Trace {
    Event events[16];
    const char *stages[15];
    const char *passes[15];
    int count = 0;
    void begin() {
        count = 0;
        CK(cudaEventRecord(events[0].e));
    }
    void mark(const char *stage, const char *pass) {
        if (count >= 15)
            throw std::runtime_error("stage trace capacity exceeded");
        stages[count] = stage;
        passes[count] = pass;
        ++count;
        CK(cudaEventRecord(events[count].e));
    }
    void reconstructStages(Input &in, Work &work, Params p, const char *pass,
                           int x0 = 0, int y0 = 0) {
        int w = work.w, h = work.h;
        int sw = std::min(in.w - x0, w + int(std::ceil(p.d)));
        clearKernel<<<grid(w, h), block>>>(work.temporal.p, work.spatial.p, work.out.p,
                                           work.z.p, work.mask.p, w, h);
        mark("clear", pass);
        temporalKernel<<<grid(w, h), block>>>(in.prev.p, in.flow.p, work.temporal.p,
                                              in.w, in.h, w, h, x0, y0, p);
        mark("inter_frame", pass);
        disparityKernel<<<grid(sw, h), block>>>(in.left.p, in.depth.p, work.spatial.p,
                                                work.z.p, in.w, in.h, w, h, x0, y0, sw, p);
        mark("intra_frame", pass);
        compositeKernel<<<grid(w, h), block>>>(work.temporal.p, work.spatial.p,
                                               work.mask.p, w, h);
        fillKernel<<<grid(w, h), block>>>(work.spatial.p, work.mask.p, work.out.p, w, h);
        mark("composite_fill", pass);
        CK(cudaGetLastError());
    }
    Byte *run(Pipeline &p, int mode, Params params) {
        begin();
        if (mode == 0) {
            reconstructStages(p.full, p.fullWork, params, "full");
            return p.fullWork.out.p;
        }
        p.downsample();
        mark("downsample", "base");
        Params half = {params.d * 0.5, params.umax * 0.5, params.vmax * 0.5,
                       params.umin * 0.5, params.vmin * 0.5};
        reconstructStages(p.half, p.halfWork, half, "base");
        if (p.fastResample)
            upsampleKernel<float, true><<<dim3((p.full.w + 31) / 32, (p.full.h + 7) / 8),
                                         dim3(32, 8)>>>(
                p.halfWork.out.p, p.output.p, p.half.w, p.half.h, p.full.w, p.full.h);
        else
            upsampleKernel<double><<<grid(p.full.w, p.full.h), block>>>(
                p.halfWork.out.p, p.output.p, p.half.w, p.half.h, p.full.w, p.full.h);
        mark("upsample", "base");
        if (mode == 2) {
            reconstructStages(p.full, p.roi, params, "roi", p.x0, p.y0);
            overlayKernel<<<grid(p.cw, p.ch), block>>>(p.roi.out.p, p.output.p, p.roi.w,
                                                       p.full.w, p.x0, p.y0, p.cw, p.ch, 8);
            mark("overlay", "roi");
        }
        CK(cudaGetLastError());
        return p.output.p;
    }
};

std::vector<std::string> inputs(const Options &o) {
    if (!o.input.empty()) return {o.input};
    std::ifstream manifest(o.manifest);
    if (!manifest) throw std::runtime_error("cannot open manifest");
    const auto slash = o.manifest.find_last_of("/\\");
    const std::string parent = slash == std::string::npos ? "" : o.manifest.substr(0, slash + 1);
    std::vector<std::string> paths;
    std::string line;
    while (std::getline(manifest, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty() || line[0] == '#') continue;
        bool absolute = line[0] == '/' || line[0] == '\\' || (line.size() > 1 && line[1] == ':');
        paths.push_back(absolute ? line : parent + line);
    }
    if (paths.empty()) throw std::runtime_error("empty manifest");
    return paths;
}

struct Sample {
    double wall = 0, reconstructionWall = 0, h2dApi = 0, d2hApi = 0;
    double reconstructionGPU = 0, totalGPU = 0, h2dGPU = 0, d2hGPU = 0;
};

Sample measure(Pipeline &p, Frame &f, int mode, bool instrumented, bool stream,
               Trace &trace, Event &totalStart, Event &reconStart,
               Event &reconEnd, Event &totalEnd, std::vector<Byte> &host) {
    Sample s;
    auto t0 = Clock::now();
    CK(cudaEventRecord(totalStart.e));
    if (stream) {
        auto a = Clock::now();
        p.full.upload(f);
        s.h2dApi = milliseconds(a, Clock::now());
    }
    CK(cudaEventRecord(reconStart.e));
    auto beginRecon = Clock::now();
    Byte *output = instrumented ? trace.run(p, mode, f.p) : p.run(mode, f.p);
    CK(cudaEventRecord(reconEnd.e));
    auto endRecon = Clock::now();
    // This is CPU launch/enqueue time, not completed GPU reconstruction time.
    s.reconstructionWall = milliseconds(beginRecon, endRecon);
    if (stream) {
        auto a = Clock::now();
        CK(cudaMemcpy(host.data(), output, host.size(), cudaMemcpyDeviceToHost));
        s.d2hApi = milliseconds(a, Clock::now());
    }
    CK(cudaEventRecord(totalEnd.e));
    CK(cudaEventSynchronize(totalEnd.e));
    s.wall = milliseconds(t0, Clock::now());
    s.totalGPU = elapsed(totalStart, totalEnd);
    s.reconstructionGPU = elapsed(reconStart, reconEnd);
    if (stream) {
        s.h2dGPU = elapsed(totalStart, reconStart);
        s.d2hGPU = elapsed(reconEnd, totalEnd);
    }
    return s;
}

void write(std::ostream &csv, const std::string &frame, const char *mode, int iteration,
           const char *variant, const char *stage, const char *pass, double gpu,
           const Sample &s, const Options &o) {
    csv << frame << ',' << mode << ',' << iteration << ',' << variant << ',' << stage
        << ',' << pass << ',' << gpu << ',' << s.wall << ',' << s.reconstructionWall
        << ',' << s.h2dApi << ',' << s.d2hApi << ',' << o.rw << ',' << o.rh << ','
        << (o.stream ? "host_transfer" : "gpu_resident") << ',' << o.fast << '\n';
}
} // namespace stage_profile

int main(int argc, char **argv) {
    using namespace stage_profile;
    try {
        for (int i = 1; i < argc; ++i) {
            if (std::string(argv[i]) == "--help") {
                std::cout << "profile_stages --input FILE | --manifest PATH --csv NEW.csv "
                             "[--roi-width 160 --roi-height 90 --repeats 100 --warmup 10 "
                             "--fast-resample --stream]\n"
                             "Alternates reference and staged measurements, writes raw GPU stage "
                             "times and CPU wall diagnostics. Decoding is not measured.\n";
                return 0;
            }
        }
        Options o = parse(argc, argv);
        if (o.pre || !o.dump.empty())
            throw std::runtime_error("profiler does not support precomputed base or image dumps");
        if (o.self) { selfTest(); return 0; }
        if (std::ifstream(o.csv).good())
            throw std::runtime_error("output already exists; choose a new CSV path");
        auto paths = inputs(o);
        std::ofstream csv(o.csv);
        if (!csv) throw std::runtime_error("cannot create CSV");
        csv << "frame,mode,iteration,variant,stage,pass,gpu_ms,wall_total_ms,"
               "cpu_reconstruction_enqueue_ms,h2d_api_wall_ms,d2h_api_wall_ms,"
               "roi_width,roi_height,timing,fast_resample\n" << std::setprecision(10);
        const char *names[] = {"full", "half_base", "fov"};
        for (const auto &path : paths) {
            Frame f = load(path);
            int cx = o.cx < 0 ? f.w / 2 : o.cx, cy = o.cy < 0 ? f.h / 2 : o.cy;
            if (o.rw > f.w - 6 || o.rh > f.h - 6 || cx - o.rw / 2 - 3 < 0 ||
                cy - o.rh / 2 - 3 < 0 || cx - o.rw / 2 + o.rw + 3 > f.w ||
                cy - o.rh / 2 + o.rh + 3 > f.h)
                throw std::runtime_error("ROI + 3px halo must fit frame");
            Pipeline p(f.w, f.h, o.rw, o.rh, cx, cy, false);
            p.fastResample = o.fast;
            p.full.upload(f);
            CK(cudaDeviceSynchronize());
            Trace trace;
            Event totalStart, reconStart, reconEnd, totalEnd;
            std::vector<Byte> host(size_t(f.w) * f.h * 3);
            auto slash = path.find_last_of("/\\");
            std::string frame = path.substr(slash == std::string::npos ? 0 : slash + 1);
            std::vector<double> walls[3][2];
            for (int r = -o.warmup; r < o.repeats; ++r) {
                int sequence = r + o.warmup;
                for (int offset = 0; offset < 3; ++offset) {
                    int mode = (sequence + offset) % 3;
                    for (int which = 0; which < 2; ++which) {
                        int instrumented = (sequence + offset + which) % 2;
                        Sample s = measure(p, f, mode, instrumented, o.stream, trace,
                                           totalStart, reconStart, reconEnd, totalEnd, host);
                        if (r < 0) continue;
                        walls[mode][instrumented].push_back(s.wall);
                        const char *variant = instrumented ? "staged" : "reference";
                        write(csv, frame, names[mode], r, variant, "total", "all", s.totalGPU, s, o);
                        write(csv, frame, names[mode], r, variant, "reconstruction", "all",
                              s.reconstructionGPU, s, o);
                        if (o.stream) {
                            write(csv, frame, names[mode], r, variant, "h2d", "all", s.h2dGPU, s, o);
                            write(csv, frame, names[mode], r, variant, "d2h", "all", s.d2hGPU, s, o);
                        }
                        if (instrumented) {
                            double sum = 0;
                            for (int k = 0; k < trace.count; ++k) {
                                double duration = elapsed(trace.events[k], trace.events[k + 1]);
                                sum += duration;
                                write(csv, frame, names[mode], r, variant, trace.stages[k],
                                      trace.passes[k], duration, s, o);
                            }
                            // Covers the two outer boundary events around the inner trace.
                            write(csv, frame, names[mode], r, variant, "trace_boundary", "all",
                                  s.reconstructionGPU - sum, s, o);
                        }
                    }
                }
            }
            for (int m = 0; m < 3; ++m)
                for (int v = 0; v < 2; ++v) {
                    const auto &a = walls[m][v];
                    double mean = std::accumulate(a.begin(), a.end(), 0.0) / a.size();
                    std::cout << frame << ' ' << names[m] << ' ' << (v ? "staged" : "reference")
                              << " mean_wall_ms=" << mean << " samples=" << a.size() << '\n';
                }
            csv.flush();
            if (!csv) throw std::runtime_error("CSV write failed");
        }
        std::cout << "COMPLETE: " << paths.size() << " frames\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "ERROR: " << e.what() << '\n';
        return 1;
    }
}
