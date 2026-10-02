// CUDA C++14 port of the current Numba speed prototype. See ../README.md.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <cuda_runtime.h>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#define CK(call)                                                                                   \
    do {                                                                                           \
        cudaError_t cuda_status_ = (call);                                                         \
        if (cuda_status_ != cudaSuccess)                                                           \
            throw std::runtime_error(std::string(#call) + ": " +                                   \
                                     cudaGetErrorString(cuda_status_));                            \
    } while (0)
using Byte = unsigned char;
struct Params {
    double d, umax, vmax, umin, vmin;
};
struct Frame {
    int w, h;
    Params p;
    std::vector<Byte> left, prev, gt;
    std::vector<uint16_t> depth, flow;
};
template <class T> struct Buffer {
    T *p = nullptr;
    size_t n;
    explicit Buffer(size_t count) : n(count) {
        CK(cudaMalloc(reinterpret_cast<void **>(&p), n * sizeof(T)));
    }
    ~Buffer() {
        if (p)
            cudaFree(p);
    }
    Buffer(const Buffer &) = delete;
    Buffer &operator=(const Buffer &) = delete;
    void upload(const std::vector<T> &v) {
        if (v.size() != n)
            throw std::runtime_error("upload size");
        CK(cudaMemcpy(p, v.data(), n * sizeof(T), cudaMemcpyHostToDevice));
    }
};
struct Input {
    int w, h;
    Buffer<Byte> left, prev;
    Buffer<uint16_t> depth, flow;
    Input(int W, int H)
        : w(W), h(H), left(W * H * 3), prev(W * H * 3), depth(W * H), flow(W * H * 2) {}
    void upload(const Frame &f) {
        left.upload(f.left);
        prev.upload(f.prev);
        depth.upload(f.depth);
        flow.upload(f.flow);
    }
};
struct Work {
    int w, h;
    Buffer<Byte> temporal, spatial, out, z, mask;
    Work(int W, int H)
        : w(W), h(H), temporal(W * H * 3), spatial(W * H * 3), out(W * H * 3), z(W * H),
          mask(W * H) {}
};
// Row is CUDA x, as in the existing Numba (32,32) launch layout.
dim3 grid(int w, int h) {
    return dim3((h + 31) / 32, (w + 31) / 32);
}
const dim3 block(32, 32);
__global__ void clearKernel(Byte *a, Byte *b, Byte *out, Byte *z, Byte *mask, int w, int h) {
    int y = blockIdx.x * blockDim.x + threadIdx.x, x = blockIdx.y * blockDim.y + threadIdx.y;
    if (x >= w || y >= h)
        return;
    int i = y * w + x;
    z[i] = mask[i] = 0;
    for (int c = 0; c < 3; c++)
        a[i * 3 + c] = b[i * 3 + c] = out[i * 3 + c] = 0;
}
__global__ void temporalKernel(const Byte *prev, const uint16_t *flow, Byte *out, int W, int H,
                               int w, int h, int x0, int y0, Params p) {
    int y = blockIdx.x * blockDim.x + threadIdx.x, x = blockIdx.y * blockDim.y + threadIdx.y;
    if (x >= w || y >= h)
        return;
    int source = (y + y0) * W + x + x0;
    int u = static_cast<int>(
        nearbyint(double(flow[source * 2]) / 65535.0 * (p.umax - p.umin) + p.umin));
    int v = static_cast<int>(
        nearbyint(double(flow[source * 2 + 1]) / 65535.0 * (p.vmax - p.vmin) + p.vmin));
    int sx = x + x0 + u, sy = y + y0 + v;
    if (sx < 0 || sx >= W || sy < 0 || sy >= H)
        return;
    for (int c = 0; c < 3; c++)
        out[(y * w + x) * 3 + c] = prev[(sy * W + sx) * 3 + c];
}
__global__ void disparityKernel(const Byte *left, const uint16_t *depth, Byte *out, Byte *z, int W,
                                int H, int w, int h, int x0, int y0, int sw, Params p) {
    int y = blockIdx.x * blockDim.x + threadIdx.x, x = blockIdx.y * blockDim.y + threadIdx.y;
    if (y >= h || x >= sw || x + x0 >= W || y + y0 >= H)
        return;
    int s = (y + y0) * W + x + x0;
    int d = static_cast<int>(nearbyint(double(depth[s]) * p.d / 65535.0)), dx = x - d;
    if (dx < 0 || dx >= w)
        return;
    int t = y * w + dx;
    // Intentional compatibility: original uint8 depth buffer and competing
    // writes are retained. This is not a deterministic z-buffer implementation.
    if (z[t] == 0 || z[t] < depth[s]) {
        for (int c = 0; c < 3; c++)
            out[t * 3 + c] = left[s * 3 + c];
        z[t] = static_cast<Byte>(depth[s]);
    }
}
__global__ void compositeKernel(const Byte *temporal, Byte *spatial, Byte *mask, int w, int h) {
    int y = blockIdx.x * blockDim.x + threadIdx.x, x = blockIdx.y * blockDim.y + threadIdx.y;
    if (x >= w || y >= h)
        return;
    int i = y * w + x;
    mask[i] = 0;
    if (int(spatial[3 * i]) + spatial[3 * i + 1] + spatial[3 * i + 2] == 0) {
        if (int(temporal[3 * i]) + temporal[3 * i + 1] + temporal[3 * i + 2] == 0)
            mask[i] = 1;
        for (int c = 0; c < 3; c++)
            spatial[3 * i + c] = temporal[3 * i + c];
    }
}
__global__ void fillKernel(const Byte *src, const Byte *mask, Byte *out, int w, int h) {
    int y = blockIdx.x * blockDim.x + threadIdx.x, x = blockIdx.y * blockDim.y + threadIdx.y;
    if (x >= w || y >= h)
        return;
    int i = y * w + x;
    if (!mask[i]) {
        for (int c = 0; c < 3; c++)
            out[3 * i + c] = src[3 * i + c];
        return;
    }
    int sum[3] = {0, 0, 0}, n = 0;
    for (int dy = -3; dy <= 3; dy++)
        for (int dx = -3; dx <= 3; dx++) {
            int yy = y + dy, xx = x + dx;
            if (yy < 0 || yy >= h || xx < 0 || xx >= w)
                continue;
            int j = yy * w + xx;
            if (!mask[j]) {
                for (int c = 0; c < 3; c++)
                    sum[c] += src[3 * j + c];
                n++;
            }
        }
    if (n)
        for (int c = 0; c < 3; c++)
            out[3 * i + c] = static_cast<Byte>(nearbyint(double(sum[c]) / n));
}
__global__ void downsampleKernel(const Byte *left, const Byte *prev, const uint16_t *depth,
                                 const uint16_t *flow, Byte *l2, Byte *p2, uint16_t *d2,
                                 uint16_t *f2, int W, int w, int h) {
    int y = blockIdx.x * blockDim.x + threadIdx.x, x = blockIdx.y * blockDim.y + threadIdx.y;
    if (x >= w || y >= h)
        return;
    int s = (2 * y + 1) * W + 2 * x + 1, t = y * w + x;
    for (int c = 0; c < 3; c++) {
        l2[3 * t + c] = left[3 * s + c];
        p2[3 * t + c] = prev[3 * s + c];
    }
    d2[t] = depth[s];
    f2[2 * t] = flow[2 * s];
    f2[2 * t + 1] = flow[2 * s + 1];
}
__global__ void upsampleKernel(const Byte *src, Byte *dst, int w, int h, int W, int H) {
    int y = blockIdx.x * blockDim.x + threadIdx.x, x = blockIdx.y * blockDim.y + threadIdx.y;
    if (x >= W || y >= H)
        return;
    double yy = fmax(0.0, fmin(double(h - 1), (y + 0.5) * h / H - 0.5));
    double xx = fmax(0.0, fmin(double(w - 1), (x + 0.5) * w / W - 0.5));
    int y0 = int(yy), x0 = int(xx), y1 = min(y0 + 1, h - 1), x1 = min(x0 + 1, w - 1);
    double fy = yy - y0, fx = xx - x0;
    for (int c = 0; c < 3; c++) {
        double top = src[(y0 * w + x0) * 3 + c] * (1 - fx) + src[(y0 * w + x1) * 3 + c] * fx;
        double bot = src[(y1 * w + x0) * 3 + c] * (1 - fx) + src[(y1 * w + x1) * 3 + c] * fx;
        dst[(y * W + x) * 3 + c] = static_cast<Byte>(top * (1 - fy) + bot * fy + 0.5);
    }
}
__global__ void overlayKernel(const Byte *roi, Byte *dst, int rw, int W, int x0, int y0, int cw,
                              int ch, int feather) {
    int y = blockIdx.x * blockDim.x + threadIdx.x, x = blockIdx.y * blockDim.y + threadIdx.y;
    if (x >= cw || y >= ch)
        return;
    int edge = min(min(x, y), min(cw - 1 - x, ch - 1 - y));
    double a = fmin(1.0, double(edge + 1) / feather);
    for (int c = 0; c < 3; c++) {
        int t = ((y0 + 3 + y) * W + x0 + 3 + x) * 3 + c;
        dst[t] =
            static_cast<Byte>(dst[t] * (1 - a) + roi[((y + 3) * rw + x + 3) * 3 + c] * a + 0.5);
    }
}
void reconstruct(Input &in, Work &work, Params p, int x0 = 0, int y0 = 0) {
    int w = work.w, h = work.h, sw = std::min(in.w - x0, w + int(std::ceil(p.d)));
    clearKernel<<<grid(w, h), block>>>(work.temporal.p, work.spatial.p, work.out.p, work.z.p,
                                       work.mask.p, w, h);
    temporalKernel<<<grid(w, h), block>>>(in.prev.p, in.flow.p, work.temporal.p, in.w, in.h, w, h,
                                          x0, y0, p);
    disparityKernel<<<grid(sw, h), block>>>(in.left.p, in.depth.p, work.spatial.p, work.z.p, in.w,
                                            in.h, w, h, x0, y0, sw, p);
    compositeKernel<<<grid(w, h), block>>>(work.temporal.p, work.spatial.p, work.mask.p, w, h);
    fillKernel<<<grid(w, h), block>>>(work.spatial.p, work.mask.p, work.out.p, w, h);
    CK(cudaGetLastError());
}
struct Pipeline {
    Input full, half;
    Work fullWork, halfWork, roi;
    Buffer<Byte> output;
    int cw, ch, x0, y0;
    bool precomputed;
    Pipeline(int w, int h, int CW, int CH, int cx, int cy, bool pre)
        : full(w, h), half(w / 2, h / 2), fullWork(w, h), halfWork(w / 2, h / 2),
          roi(CW + 6, CH + 6), output(w * h * 3), cw(CW), ch(CH), x0(cx - CW / 2 - 3),
          y0(cy - CH / 2 - 3), precomputed(pre) {}
    void downsample() {
        downsampleKernel<<<grid(half.w, half.h), block>>>(
            full.left.p, full.prev.p, full.depth.p, full.flow.p, half.left.p, half.prev.p,
            half.depth.p, half.flow.p, full.w, half.w, half.h);
        CK(cudaGetLastError());
    }
    Byte *run(int mode, Params p) {
        if (mode == 0) {
            reconstruct(full, fullWork, p);
            return fullWork.out.p;
        }
        if (!precomputed)
            downsample();
        Params hp = {p.d * 0.5, p.umax * 0.5, p.vmax * 0.5, p.umin * 0.5, p.vmin * 0.5};
        reconstruct(half, halfWork, hp);
        upsampleKernel<<<grid(full.w, full.h), block>>>(halfWork.out.p, output.p, half.w, half.h,
                                                        full.w, full.h);
        if (mode == 2) {
            reconstruct(full, roi, p, x0, y0);
            overlayKernel<<<grid(cw, ch), block>>>(roi.out.p, output.p, roi.w, full.w, x0, y0, cw,
                                                   ch, 8);
        }
        CK(cudaGetLastError());
        return output.p;
    }
};
template <class T> void readExact(std::ifstream &in, T *p, size_t n) {
    if (!in.read(reinterpret_cast<char *>(p), std::streamsize(n * sizeof(T))))
        throw std::runtime_error("truncated frame");
}
Frame load(const std::string &path) {
    std::ifstream in(path, std::ios::binary);
    if (!in)
        throw std::runtime_error("cannot open " + path);
    char magic[8];
    uint32_t w, h;
    Frame f;
    readExact(in, magic, 8);
    readExact(in, &w, 1);
    readExact(in, &h, 1);
    if (std::memcmp(magic, "PIRFRM1\0", 8) || w < 8 || h < 8 || w > 8192 || h > 8192 || w % 2 ||
        h % 2)
        throw std::runtime_error("invalid header or dimensions");
    f.w = int(w);
    f.h = int(h);
    double p[5];
    readExact(in, p, 5);
    for (double x : p)
        if (!std::isfinite(x) || std::abs(x) > 100000)
            throw std::runtime_error("invalid motion parameter");
    if (p[0] < 0)
        throw std::runtime_error("negative disparity bound");
    f.p = {p[0], p[1], p[2], p[3], p[4]};
    size_t n = size_t(w) * h;
    f.left.resize(n * 3);
    f.prev.resize(n * 3);
    f.depth.resize(n);
    f.flow.resize(n * 2);
    f.gt.resize(n * 3);
    readExact(in, f.left.data(), n * 3);
    readExact(in, f.prev.data(), n * 3);
    readExact(in, f.depth.data(), n);
    readExact(in, f.flow.data(), n * 2);
    readExact(in, f.gt.data(), n * 3);
    if (in.peek() != std::char_traits<char>::eof())
        throw std::runtime_error("unexpected trailing frame bytes");
    return f;
}
double legacyPSNR(const std::vector<Byte> &a, const std::vector<Byte> &b) {
    // Preserve NumPy uint8 subtraction and uint8 square overflow, deliberately.
    uint64_t sum = 0;
    for (size_t i = 0; i < a.size(); i++) {
        unsigned d = (unsigned(a[i]) - unsigned(b[i])) & 255u;
        sum += (d * d) & 255u;
    }
    if (sum == 0)
        return std::numeric_limits<double>::infinity();
    return 20 * std::log10(255.0 / std::sqrt(double(sum) / a.size()));
}
void ppm(const std::string &path, const std::vector<Byte> &bgr, int w, int h) {
    std::ofstream out(path, std::ios::binary);
    if (!out)
        throw std::runtime_error("cannot write " + path);
    out << "P6\n" << w << " " << h << "\n255\n";
    for (size_t i = 0; i < bgr.size(); i += 3) {
        char rgb[3] = {char(bgr[i + 2]), char(bgr[i + 1]), char(bgr[i])};
        out.write(rgb, 3);
    }
    if (!out)
        throw std::runtime_error("image write failed");
}
double percentile(std::vector<double> v, double q) {
    std::sort(v.begin(), v.end());
    double i = q * (v.size() - 1);
    size_t lo = size_t(i), hi = std::min(lo + 1, v.size() - 1);
    return v[lo] + (v[hi] - v[lo]) * (i - lo);
}
struct Options {
    std::string manifest, input, csv = "timings.csv", dump;
    int repeats = 100, warmup = 10, rw = 160, rh = 90, cx = -1, cy = -1;
    bool pre = false, stream = false, self = false;
};
Options parse(int argc, char **argv) {
    Options o;
    for (int i = 1; i < argc; i++) {
        std::string k = argv[i];
        if (k == "--help") {
            std::cout << "pirate_bench --manifest PATH | --input FILE [--roi-width 160 "
                         "--roi-height 90 --center-x X --center-y Y --repeats 100 --warmup 10 "
                         "--csv timings.csv --dump-prefix PATH --stream --precomputed-base]\n      "
                         " pirate_bench --self-test\n";
            std::exit(0);
        }
        if (k == "--precomputed-base") {
            o.pre = true;
            continue;
        }
        if (k == "--stream") {
            o.stream = true;
            continue;
        }
        if (k == "--self-test") {
            o.self = true;
            continue;
        }
        if (i + 1 >= argc)
            throw std::runtime_error("missing value for " + k);
        std::string v = argv[++i];
        if (k == "--manifest")
            o.manifest = v;
        else if (k == "--input")
            o.input = v;
        else if (k == "--csv")
            o.csv = v;
        else if (k == "--dump-prefix")
            o.dump = v;
        else if (k == "--repeats")
            o.repeats = std::stoi(v);
        else if (k == "--warmup")
            o.warmup = std::stoi(v);
        else if (k == "--roi-width")
            o.rw = std::stoi(v);
        else if (k == "--roi-height")
            o.rh = std::stoi(v);
        else if (k == "--center-x")
            o.cx = std::stoi(v);
        else if (k == "--center-y")
            o.cy = std::stoi(v);
        else
            throw std::runtime_error("unknown option " + k);
    }
    if (o.repeats < 1 || o.warmup < 1 || o.rw < 1 || o.rh < 1)
        throw std::runtime_error("positive counts/sizes required");
    if (o.pre && o.stream)
        throw std::runtime_error("--precomputed-base is only for GPU-resident timing");
    if (!o.self && (o.manifest.empty() == o.input.empty()))
        throw std::runtime_error("specify exactly one of --input/--manifest");
    return o;
}
struct Event {
    cudaEvent_t e;
    Event() {
        CK(cudaEventCreate(&e));
    }
    ~Event() {
        cudaEventDestroy(e);
    }
};
std::vector<Byte> referenceFull(const Frame &f) {
    int w = f.w, h = f.h;
    std::vector<Byte> t(w * h * 3, 0), s(w * h * 3, 0), out(w * h * 3, 0), z(w * h, 0),
        mask(w * h, 0);
    for (int y = 0; y < h; y++)
        for (int x = 0; x < w; x++) {
            int i = y * w + x;
            int u = int(
                std::nearbyint(double(f.flow[2 * i]) / 65535 * (f.p.umax - f.p.umin) + f.p.umin));
            int v = int(std::nearbyint(double(f.flow[2 * i + 1]) / 65535 * (f.p.vmax - f.p.vmin) +
                                       f.p.vmin));
            if (x + u >= 0 && x + u < w && y + v >= 0 && y + v < h)
                for (int c = 0; c < 3; c++)
                    t[3 * i + c] = f.prev[((y + v) * w + x + u) * 3 + c];
            int dx = x - int(std::nearbyint(double(f.depth[i]) * f.p.d / 65535));
            if (dx >= 0 && dx < w) {
                int j = y * w + dx;
                if (z[j] == 0 || z[j] < f.depth[i]) {
                    for (int c = 0; c < 3; c++)
                        s[3 * j + c] = f.left[3 * i + c];
                    z[j] = Byte(f.depth[i]);
                }
            }
        }
    for (int i = 0; i < w * h; i++)
        if (int(s[3 * i]) + s[3 * i + 1] + s[3 * i + 2] == 0) {
            mask[i] = (int(t[3 * i]) + t[3 * i + 1] + t[3 * i + 2] == 0);
            for (int c = 0; c < 3; c++)
                s[3 * i + c] = t[3 * i + c];
        }
    for (int y = 0; y < h; y++)
        for (int x = 0; x < w; x++) {
            int i = y * w + x;
            if (!mask[i]) {
                for (int c = 0; c < 3; c++)
                    out[3 * i + c] = s[3 * i + c];
                continue;
            }
            int sum[3] = {0, 0, 0}, n = 0;
            for (int dy = -3; dy <= 3; dy++)
                for (int dx = -3; dx <= 3; dx++) {
                    int yy = y + dy, xx = x + dx;
                    if (xx >= 0 && xx < w && yy >= 0 && yy < h && !mask[yy * w + xx]) {
                        for (int c = 0; c < 3; c++)
                            sum[c] += s[(yy * w + xx) * 3 + c];
                        n++;
                    }
                }
            if (n)
                for (int c = 0; c < 3; c++)
                    out[3 * i + c] = Byte(std::nearbyint(double(sum[c]) / n));
        }
    return out;
}
void selfTest() {
    Frame f;
    f.w = 64;
    f.h = 48;
    f.p = {0, 0, 0, 0, 0};
    size_t n = f.w * f.h;
    f.left.assign(n * 3, 80);
    f.prev.assign(n * 3, 20);
    f.gt = f.left;
    f.depth.assign(n, 0);
    f.flow.assign(n * 2, 0);
    Pipeline p(f.w, f.h, 16, 12, 32, 24, false);
    p.full.upload(f);
    std::vector<Byte> out(n * 3);
    for (int mode = 0; mode < 3; mode++) {
        Byte *d = p.run(mode, f.p);
        CK(cudaMemcpy(out.data(), d, out.size(), cudaMemcpyDeviceToHost));
        if (out != f.left)
            throw std::runtime_error("constant-image self-test failed");
    }
    // Nonconstant zero-disparity warp must reproduce every source pixel.
    for (size_t i = 0; i < f.left.size(); i++)
        f.left[i] = Byte(1 + (i * 17) % 254);
    p.full.upload(f);
    CK(cudaMemcpy(out.data(), p.run(0, f.p), out.size(), cudaMemcpyDeviceToHost));
    if (out != f.left)
        throw std::runtime_error("identity warp self-test failed");
    f.p = {2, 1, 0, 1, 0};
    std::fill(f.depth.begin(), f.depth.end(), 65535);
    p.full.upload(f);
    CK(cudaMemcpy(out.data(), p.run(0, f.p), out.size(), cudaMemcpyDeviceToHost));
    if (out != referenceFull(f))
        throw std::runtime_error("disparity/flow/fill CPU-reference test failed");
    std::vector<Byte> reference = referenceFull(f), base(out.size());
    CK(cudaMemcpy(base.data(), p.run(1, f.p), base.size(), cudaMemcpyDeviceToHost));
    CK(cudaMemcpy(out.data(), p.run(2, f.p), out.size(), cudaMemcpyDeviceToHost));
    for (int y = 0; y < f.h; y++)
        for (int x = 0; x < f.w; x++) {
            int rx = x - (p.x0 + 3), ry = y - (p.y0 + 3);
            bool inside = rx >= 0 && rx < p.cw && ry >= 0 && ry < p.ch;
            double weight =
                inside ? std::min(1.0, double(std::min(std::min(rx, ry),
                                                       std::min(p.cw - 1 - rx, p.ch - 1 - ry)) +
                                              1) /
                                           8)
                       : 0;
            for (int c = 0; c < 3; c++) {
                int i = (y * f.w + x) * 3 + c;
                Byte expected =
                    inside ? Byte(base[i] * (1 - weight) + reference[i] * weight + 0.5) : base[i];
                if (out[i] != expected)
                    throw std::runtime_error("ROI coverage/feather reference test failed");
            }
        }
    // Preserve original PSNR overflow: (0-255) modulo 256 is 1.
    std::vector<Byte> a(3, 0), b(3, 255);
    if (std::abs(legacyPSNR(a, b) - 20 * std::log10(255.0)) > 1e-10)
        throw std::runtime_error("PSNR wrap self-test failed");
    if (!std::isinf(legacyPSNR(a, a)))
        throw std::runtime_error("zero-MSE PSNR test failed");
    std::cout << "SELF_TEST_OK: constant full/base/FOV, identity warp, translated "
                 "disparity/flow/fill CPU reference, ROI coverage/feather, legacy PSNR wrap/zero\n";
}
int main(int argc, char **argv) {
    try {
        Options o = parse(argc, argv);
        cudaDeviceProp device;
        CK(cudaGetDeviceProperties(&device, 0));
        std::cout << "GPU=" << device.name << " SM=" << device.major << device.minor << "\n";
        if (o.self) {
            selfTest();
            return 0;
        }
        std::vector<std::string> paths;
        if (!o.input.empty())
            paths.push_back(o.input);
        else {
            std::ifstream list(o.manifest);
            if (!list)
                throw std::runtime_error("cannot open manifest");
            size_t slash = o.manifest.find_last_of("/\\");
            std::string parent = slash == std::string::npos ? "" : o.manifest.substr(0, slash + 1),
                        line;
            while (std::getline(list, line)) {
                if (!line.empty() && line.back() == '\r')
                    line.pop_back();
                if (line.empty() || line[0] == '#')
                    continue;
                paths.push_back(parent + line);
            }
        }
        if (paths.empty())
            throw std::runtime_error("empty manifest");
        std::ofstream csv(o.csv);
        if (!csv)
            throw std::runtime_error("cannot write CSV");
        csv << "frame,mode,iteration,wall_ms,gpu_timeline_ms,legacy_right_psnr_db,roi_width,roi_"
               "height,timing,downsample_included\n"
            << std::setprecision(10);
        const char *names[] = {"full", "half_base", "fov"};
        for (size_t fi = 0; fi < paths.size(); fi++) {
            Frame f = load(paths[fi]);
            int cx = o.cx < 0 ? f.w / 2 : o.cx, cy = o.cy < 0 ? f.h / 2 : o.cy;
            if (o.rw > f.w - 6 || o.rh > f.h - 6 || cx - o.rw / 2 - 3 < 0 ||
                cy - o.rh / 2 - 3 < 0 || cx - o.rw / 2 + o.rw + 3 > f.w ||
                cy - o.rh / 2 + o.rh + 3 > f.h)
                throw std::runtime_error("ROI + 3px halo must fit frame");
            Pipeline p(f.w, f.h, o.rw, o.rh, cx, cy, o.pre);
            p.full.upload(f);
            if (o.pre)
                p.downsample();
            CK(cudaDeviceSynchronize());
            std::vector<Byte> host(size_t(f.w) * f.h * 3);
            Event start, end;
            for (int r = 0; r < o.warmup; r++)
                for (int m = 0; m < 3; m++) {
                    p.run(m, f.p);
                    CK(cudaDeviceSynchronize());
                }
            std::vector<double> walls[3], gpus[3];
            std::vector<std::vector<Byte>> images(3);
            double scores[3];
            for (int r = 0; r < o.repeats; r++)
                for (int offset = 0; offset < 3; offset++) {
                    int m = (r + offset) % 3;
                    auto t = std::chrono::steady_clock::now();
                    if (o.stream)
                        p.full.upload(f);
                    CK(cudaEventRecord(start.e));
                    Byte *out = p.run(m, f.p);
                    CK(cudaEventRecord(end.e));
                    if (o.stream)
                        CK(cudaMemcpy(host.data(), out, host.size(), cudaMemcpyDeviceToHost));
                    CK(cudaEventSynchronize(end.e));
                    auto done = std::chrono::steady_clock::now();
                    float gpu;
                    CK(cudaEventElapsedTime(&gpu, start.e, end.e));
                    walls[m].push_back(std::chrono::duration<double, std::milli>(done - t).count());
                    gpus[m].push_back(gpu);
                    if (r == o.repeats - 1) {
                        if (!o.stream)
                            CK(cudaMemcpy(host.data(), out, host.size(), cudaMemcpyDeviceToHost));
                        images[m] = host;
                        scores[m] = legacyPSNR(host, f.gt);
                    }
                }
            size_t slash = paths[fi].find_last_of("/\\");
            std::string name = paths[fi].substr(slash == std::string::npos ? 0 : slash + 1);
            for (int m = 0; m < 3; m++) {
                for (int r = 0; r < o.repeats; r++)
                    csv << name << ',' << names[m] << ',' << r << ',' << walls[m][r] << ','
                        << gpus[m][r] << ',' << scores[m] << ',' << o.rw << ',' << o.rh << ','
                        << (o.stream ? "host_transfer" : "gpu_resident") << ','
                        << (!o.pre && m != 0) << '\n';
                std::cout << name << " " << names[m]
                          << " wall p50/p95/p99=" << percentile(walls[m], .5) << "/"
                          << percentile(walls[m], .95) << "/" << percentile(walls[m], .99)
                          << " ms legacy_right_PSNR=" << scores[m] << '\n';
                if (!o.dump.empty())
                    ppm(o.dump + "_" + std::to_string(fi) + "_" + names[m] + ".ppm", images[m], f.w,
                        f.h);
            }
        }
        if (!csv)
            throw std::runtime_error("CSV write failed");
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "ERROR: " << e.what() << '\n';
        return 1;
    }
}
