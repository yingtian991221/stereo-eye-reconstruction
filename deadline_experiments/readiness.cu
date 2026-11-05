// Synthetic decoded-input readiness, real CUDA executions and host timestamps.
// Reuse the project's kernels. No decoder, network or physical display here.
#define main archived_benchmark_main
#include "../jetson_cuda/pirate_bench.cu"
#undef main
#include <array>
#include <atomic>
#include <condition_variable>
#include <memory>
#include <mutex>
#include <thread>
#include <zlib.h>

using Clock = std::chrono::steady_clock;
using Time = Clock::time_point;
double millis(Time a, Time b) { return std::chrono::duration<double,std::milli>(a-b).count(); }
Time at(Time t, double ms) { return t+std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double,std::milli>(ms)); }
void gzreadAll(gzFile f, void *p, size_t n) {
    auto *b=static_cast<char*>(p);
    while(n) { int k=gzread(f,b,unsigned(std::min(n,size_t(1<<26)))); if(k<=0) throw std::runtime_error("truncated clip"); b+=k; n-=k; }
}
struct Sample {
    uint32_t frame, target;
    Params params;
    std::vector<Byte> src, gt[2];
    std::vector<uint16_t> depth,flow;
    std::unique_ptr<Input> gpu;
    std::unique_ptr<Buffer<Byte>> generated;
};
struct Clip {
    uint32_t w,h,n,start;
    std::vector<Byte> boot[2];
    std::vector<Sample> frames;
    explicit Clip(const std::string &path) {
        gzFile f=gzopen(path.c_str(),"rb"); if(!f)throw std::runtime_error("cannot read clip");
        char magic[8];gzreadAll(f,magic,8);
        if(memcmp(magic,"PIRSEQ2\0",8))throw std::runtime_error("clip magic");
        gzreadAll(f,&w,4);gzreadAll(f,&h,4);gzreadAll(f,&n,4);gzreadAll(f,&start,4);
        if(w!=960||h!=540||n<2||n>500)throw std::runtime_error("unsupported clip dimensions/count");
        size_t pixels=size_t(w)*h;
        for(auto &b:boot){b.resize(pixels*3);gzreadAll(f,b.data(),b.size());}
        frames.resize(n);
        for(unsigned i=0;i<n;i++) {
            auto &s=frames[i];gzreadAll(f,&s.frame,4);gzreadAll(f,&s.target,4);gzreadAll(f,&s.params,40);
            if(s.frame!=start+i||s.target!=s.frame%2)throw std::runtime_error("non-contiguous/incorrect eye order");
            s.src.resize(pixels*3);s.depth.resize(pixels);s.flow.resize(pixels*2);
            for(auto &g:s.gt)g.resize(pixels*3);
            gzreadAll(f,s.src.data(),s.src.size());gzreadAll(f,s.depth.data(),pixels*2);gzreadAll(f,s.flow.data(),pixels*4);
            for(auto &g:s.gt)gzreadAll(f,g.data(),g.size());
            s.gpu.reset(new Input(w,h));s.gpu->left.upload(s.src);s.gpu->depth.upload(s.depth);s.gpu->flow.upload(s.flow);
            s.generated.reset(new Buffer<Byte>(pixels*3));
        }
        gzclose(f);CK(cudaDeviceSynchronize());
    }
};
__global__ void orient(const Byte *src,Byte *dst,int w,int h,bool flip) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=w*h)return;
    int j=flip?(i/w*w+w-1-i%w):i;
    for(int c=0;c<3;c++)dst[3*i+c]=src[3*j+c];
}
const char *names[]={"Full","Half","FOV_0.1","FOV_0.25","FOV_0.5","FOV_0.7"};
const double scales[]={1,0,.1,.25,.5,.7};
struct Engine {
    Clip &clip;
    std::vector<std::unique_ptr<Pipeline>> pipes;
    Buffer<Byte> boot0,boot1;
    Byte *history[2];int historyId[2];
    explicit Engine(Clip &c,bool fast=true):clip(c),boot0(c.w*c.h*3),boot1(c.w*c.h*3) {
        for(int k=0;k<6;k++) {
            int rw=k<2?96:int(c.w*scales[k]),rh=k<2?54:int(c.h*scales[k]);
            pipes.emplace_back(new Pipeline(c.w,c.h,rw,rh,c.w/2,c.h/2,false));
            pipes.back()->fastClear=fast;pipes.back()->fastResample=true;
        }
        boot0.upload(c.boot[0]);boot1.upload(c.boot[1]);reset();
    }
    void reset(){history[0]=boot0.p;history[1]=boot1.p;historyId[0]=historyId[1]=int(clip.start)-1;}
    void receive(int i){auto &s=clip.frames[i];history[1-s.target]=s.gpu->left.p;historyId[1-s.target]=s.frame;}
    void run(int i,int config) {
        auto &s=clip.frames[i];auto &p=*pipes[config];size_t n=clip.w*clip.h;
        orient<<<(n+255)/256,256>>>(s.gpu->left.p,p.full.left.p,clip.w,clip.h,s.target==0);
        orient<<<(n+255)/256,256>>>(history[s.target],p.full.prev.p,clip.w,clip.h,s.target==0);
        CK(cudaMemcpyAsync(p.full.depth.p,s.gpu->depth.p,n*2,cudaMemcpyDeviceToDevice));
        CK(cudaMemcpyAsync(p.full.flow.p,s.gpu->flow.p,n*4,cudaMemcpyDeviceToDevice));
        Byte *out=p.run(config<2?config:2,s.params);
        orient<<<(n+255)/256,256>>>(out,s.generated->p,clip.w,clip.h,s.target==0);
        CK(cudaGetLastError());CK(cudaDeviceSynchronize());
    }
    void accept(int i){auto &s=clip.frames[i];history[s.target]=s.generated->p;historyId[s.target]=s.frame;}
};
struct Errors {double whole,center,boundary;};
Errors error(const std::vector<Byte> &a,const std::vector<Byte> &b,int w,int h) {
    double sum=0,center=0,edge=0;size_t nc=0,ne=0;
    // Fixed regions across policies. Separate linear passes allow compiler
    // vectorization; sums are exact integer-valued doubles below 2^53.
    int x0=w*3/8,x1=w*5/8,y0=h*3/8,y1=h*5/8;
    for(size_t i=0;i<a.size();i++){double d=double(a[i])-double(b[i]);sum+=d*d;}
    auto rect=[&](int xa,int ya,int xb,int yb){double s=0;for(int y=ya;y<yb;y++)for(int i=3*(y*w+xa);i<3*(y*w+xb);i++){double d=double(a[i])-double(b[i]);s+=d*d;}return s;};
    center=rect(x0,y0,x1,y1);nc=3*(x1-x0)*(y1-y0);
    edge=rect(x0-4,y0-4,x1+4,y1+4)-rect(x0+4,y0+4,x1-4,y1-4);
    ne=3*((x1-x0+8)*(y1-y0+8)-(x1-x0-8)*(y1-y0-8));
    return {double(sum)/a.size(),double(center)/nc,double(edge)/ne};
}
double psnr(double mse){return mse==0?std::numeric_limits<double>::infinity():10*log10(65025/mse);}
struct Estimate{double cost,whole,center;};
long gpuFrequency(){std::ifstream f("/sys/devices/17000000.gv11b/devfreq/17000000.gv11b/cur_freq");long x=-1;f>>x;return x;}
void stabilize(Engine &eng) {
    auto until=at(Clock::now(),1000);
    do {for(int k=0;k<6;k++){eng.reset();eng.receive(0);eng.run(0,k);}}while(Clock::now()<until);
    eng.reset();
}
void profile(Clip &clip,Engine &eng,const std::string &out) {
    std::ofstream f(out);f<<"frame,target,config,repeat,wall_ms,gpu_ms,stereo_mse,stereo_psnr_db,center_mse,center_psnr_db,boundary_mse\n";f<<std::setprecision(12);
    std::vector<Byte> output(clip.w*clip.h*3);Event a,b;
    for(int k=0;k<6;k++)for(int r=0;r<3;r++) {
        stabilize(eng);auto epoch=at(Clock::now(),5);
        std::vector<double> walls(clip.n);std::vector<float> gpus(clip.n);
        for(unsigned i=0;i<clip.n;i++) {
            std::this_thread::sleep_until(at(epoch,i*1000.0/90));
            eng.receive(i);Time t=Clock::now();CK(cudaEventRecord(a.e));eng.run(i,k);CK(cudaEventRecord(b.e));CK(cudaEventSynchronize(b.e));walls[i]=millis(Clock::now(),t);CK(cudaEventElapsedTime(&gpus[i],a.e,b.e));eng.accept(i);
        }
        // Defer CPU metrics so profiling has the playback duty cycle.
        for(unsigned i=0;i<clip.n;i++) {
            CK(cudaMemcpy(output.data(),clip.frames[i].generated->p,output.size(),cudaMemcpyDeviceToHost));
            auto &s=clip.frames[i];auto e=error(output,s.gt[s.target],clip.w,clip.h),d=error(s.src,s.gt[1-s.target],clip.w,clip.h);
            f<<s.frame<<','<<s.target<<','<<names[k]<<','<<r<<','<<walls[i]<<','<<gpus[i]<<','<<(e.whole+d.whole)/2<<','<<psnr((e.whole+d.whole)/2)<<','<<(e.center+d.center)/2<<','<<psnr((e.center+d.center)/2)<<','<<(e.boundary+d.boundary)/2<<'\n';
        }
    }
}
struct Plan {std::string scenario;int frame;double release,deadline;};
std::vector<std::string> split(const std::string &s){std::vector<std::string> v;std::stringstream ss(s);std::string x;while(std::getline(ss,x,','))v.push_back(x);return v;}
struct Log {double release=0,decision=0,start=0,finish=0,deadline=0,planned=0,budget=0;int config=-1,generated=0,accepted=0,display=-1,history=-1;};
int select(int policy,double budget,const std::vector<Estimate>& e) {
    if(policy<6)return policy;
    int best=-1,fastest=0;double bestq=-1e100;
    for(int k=0;k<6;k++) {
        if(e[k].cost<e[fastest].cost)fastest=k;
        double q=policy==6?e[k].whole:e[k].center;
        if(e[k].cost<=budget && (q>bestq || (q==bestq&&best>=0&&e[k].cost<e[best].cost))){best=k;bestq=q;}
    }
    return best<0?fastest:best;
}
void writePair(gzFile f,const std::vector<Byte>& left,const std::vector<Byte>& right) {
    gzwrite(f,left.data(),left.size());gzwrite(f,right.data(),right.size());
}
void replay(Clip &clip,Engine &eng,const std::vector<Plan>& plans,const std::vector<Estimate>& est,int policy,int round,const std::string &out,bool visuals) {
    if(plans.size()!=clip.n)throw std::runtime_error("plan length differs from clip");
    const std::string policyName=policy<6?names[policy]:(policy==6?"Dynamic_whole":"Dynamic_center");
    std::string stem=plans[0].scenario+"_"+policyName+"_r"+std::to_string(round);
    std::vector<Log> logs(clip.n);std::vector<bool> released(clip.n,false);std::mutex mutex;std::condition_variable cv;
    stabilize(eng);long warmFrequency=gpuFrequency();
    Time epoch=at(Clock::now(),5);
    // Producer has the entire release plan; selector receives only current
    // budget and independent profile. Future release times never reach it.
    std::thread producer([&]{for(unsigned i=0;i<clip.n;i++) {
        std::this_thread::sleep_until(at(epoch,plans[i].release));
        {std::lock_guard<std::mutex> guard(mutex);logs[i].release=millis(Clock::now(),epoch);released[i]=true;}cv.notify_all();
    }});
    int displayed=-1;
    for(unsigned i=0;i<clip.n;i++) {
        {std::unique_lock<std::mutex> lock(mutex);cv.wait(lock,[&]{return released[i];});}
        auto &l=logs[i];l.planned=plans[i].release;l.deadline=plans[i].deadline;
        eng.receive(i);l.history=eng.historyId[clip.frames[i].target];
        // Target-eye history must be the preceding decoded eye, including
        // packets that arrived too late to display. Never substitute GT.
        if(l.history!=int(clip.frames[i].frame)-1)throw std::runtime_error("history frame mismatch");
        l.decision=millis(Clock::now(),epoch);l.budget=l.deadline-l.decision;
        if(l.budget>0){l.config=select(policy,l.budget,est);l.start=millis(Clock::now(),epoch);eng.run(i,l.config);l.finish=millis(Clock::now(),epoch);l.generated=1;l.accepted=l.finish<=l.deadline;if(l.accepted){eng.accept(i);displayed=i;}}
        else {l.start=l.finish=l.decision;}
        l.display=displayed;
    }
    producer.join();
    // Offline readback, metrics and image writes cannot perturb playback.
    std::vector<std::vector<Byte>> generated(clip.n);
    for(unsigned i=0;i<clip.n;i++)if(logs[i].generated){generated[i].resize(clip.w*clip.h*3);CK(cudaMemcpy(generated[i].data(),clip.frames[i].generated->p,generated[i].size(),cudaMemcpyDeviceToHost));}
    std::ofstream f(out+"/"+stem+".csv");f<<std::setprecision(12);
    f<<"scenario,policy,round,index,frame,target,release_plan_ms,release_actual_ms,decision_ms,start_ms,finish_ms,deadline_ms,budget_ms,queue_ms,config,generated,accepted,miss,margin_ms,history_frame,display_frame,generated_stereo_mse,generated_stereo_psnr_db,generated_center_mse,display_stereo_mse,display_stereo_psnr_db,display_center_mse,display_center_psnr_db,display_boundary_mse,warm_gpu_hz\n";
    gzFile video=nullptr;if(visuals)video=gzopen((out+"/"+stem+".bgr.gz").c_str(),"wb1");
    for(unsigned i=0;i<clip.n;i++) {
        auto &s=clip.frames[i];auto &l=logs[i];Errors g{NAN,NAN,NAN};
        if(l.generated){auto a=error(generated[i],s.gt[s.target],clip.w,clip.h),b=error(s.src,s.gt[1-s.target],clip.w,clip.h);g={(a.whole+b.whole)/2,(a.center+b.center)/2,(a.boundary+b.boundary)/2};}
        std::array<const std::vector<Byte>*,2> pair{{&clip.boot[0],&clip.boot[1]}};
        int id=int(clip.start)-1;
        if(l.display>=0){auto &d=clip.frames[l.display];pair[d.target]=&generated[l.display];pair[1-d.target]=&d.src;id=d.frame;}
        auto a=error(*pair[0],s.gt[0],clip.w,clip.h),b=error(*pair[1],s.gt[1],clip.w,clip.h);Errors d{(a.whole+b.whole)/2,(a.center+b.center)/2,(a.boundary+b.boundary)/2};
        f<<plans[i].scenario<<','<<policyName<<','<<round<<','<<i<<','<<s.frame<<','<<s.target<<','<<l.planned<<','<<l.release<<','<<l.decision<<','<<l.start<<','<<l.finish<<','<<l.deadline<<','<<l.budget<<','<<l.decision-l.release<<','<<(l.config<0?"Skipped":names[l.config])<<','<<l.generated<<','<<l.accepted<<','<<!l.accepted<<','<<l.deadline-l.finish<<','<<l.history<<','<<id<<','<<g.whole<<','<<psnr(g.whole)<<','<<g.center<<','<<d.whole<<','<<psnr(d.whole)<<','<<d.center<<','<<psnr(d.center)<<','<<d.boundary<<','<<warmFrequency<<'\n';
        if(video && (policy==6 || i==0 || i+1==clip.n || i==clip.n/4-1 || i==clip.n/4 || i==clip.n/2-1 || i==clip.n/2 || i==3*clip.n/4-1 || i==3*clip.n/4))writePair(video,*pair[0],*pair[1]);
    }
    if(video)gzclose(video);
    int misses=0;for(auto &l:logs)misses+=!l.accepted;
    std::cout<<stem<<" miss="<<misses<<'/'<<clip.n<<std::endl;
}
#ifndef READINESS_NO_MAIN
int main(int argc,char**argv) {
    try {
        if(argc==2&&std::string(argv[1])=="--self-test"){selfTest();std::cout<<"original GPU self-tests PASS\n";return 0;}
        if(argc<4)throw std::runtime_error("profile CLIP OUT.csv [legacy-clear] | replay CLIP OUT PLAN.csv EST.csv ROUNDS");
        std::string mode=argv[1];Clip clip(argv[2]);Engine eng(clip,!(argc>4&&std::string(argv[4])=="legacy-clear"));
        if(mode=="profile"){profile(clip,eng,argv[3]);return 0;}
        if(mode!="replay"||argc!=7)throw std::runtime_error("invalid replay arguments");
        std::ifstream ef(argv[5]);std::string line;std::getline(ef,line);std::vector<Estimate> est;
        while(std::getline(ef,line)){auto x=split(line);if(x.size()!=4)throw std::runtime_error("estimate row");if(x[0]!=names[est.size()])throw std::runtime_error("estimate order");est.push_back({stod(x[1]),stod(x[2]),stod(x[3])});}
        if(est.size()!=6)throw std::runtime_error("six estimates required");
        std::ifstream pf(argv[4]);std::getline(pf,line);std::vector<std::vector<Plan>> scenarios;
        while(std::getline(pf,line)){auto x=split(line);if(x.size()!=4)throw std::runtime_error("plan row");if(scenarios.empty()||scenarios.back()[0].scenario!=x[0])scenarios.emplace_back();scenarios.back().push_back({x[0],stoi(x[1]),stod(x[2]),stod(x[3])});}
        for(auto &p:scenarios)for(unsigned i=0;i<p.size();i++)if(p[i].frame!=int(clip.start+i)||!std::isfinite(p[i].release)||!std::isfinite(p[i].deadline)||(i&&p[i].release<p[i-1].release))throw std::runtime_error("invalid/nonmonotonic plan");
        int rounds=std::stoi(argv[6]);
        for(int r=0;r<rounds;r++)for(size_t j=0;j<scenarios.size();j++)for(int order=0;order<8;order++) {
            int policy=(order+int(j)+r)%8;
            bool visual=r==0&&scenarios[j][0].scenario=="phase"&&(policy==0||policy==1||policy==6||policy==7);
            replay(clip,eng,scenarios[j],est,policy,r,argv[3],visual);
        }
        std::cout<<"COMPLETE\n";
    } catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}
}
#endif
