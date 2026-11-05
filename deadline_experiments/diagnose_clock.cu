// Bounded diagnostic only, not part of the deadline-miss comparison.
#define READINESS_NO_MAIN
#include "readiness.cu"
long gpuHz(){std::ifstream f("/sys/devices/17000000.gv11b/devfreq/17000000.gv11b/cur_freq");long v=-1;f>>v;return v;}
int main(int argc,char**argv){try{
    if(argc!=3)throw std::runtime_error("diagnose_clock clip output.csv");
    Clip c(argv[1]);Engine e(c);Event a,b;std::ofstream out(argv[2]);out<<"config,frame,wall_ms,gpu_ms,freq_before_hz,freq_after_hz\n"<<std::setprecision(12);
    for(int k=0;k<6;k++){
        e.reset();for(int warm=0;warm<6;warm++){e.receive(0);e.run(0,k);}e.reset();auto epoch=Clock::now();
        for(int i=0;i<32;i++){
            std::this_thread::sleep_until(at(epoch,i*1000.0/90));e.receive(i);long pre=gpuHz();auto t=Clock::now();CK(cudaEventRecord(a.e));e.run(i,k);CK(cudaEventRecord(b.e));CK(cudaEventSynchronize(b.e));double wall=millis(Clock::now(),t);float gpu;CK(cudaEventElapsedTime(&gpu,a.e,b.e));long post=gpuHz();e.accept(i);
            out<<names[k]<<','<<c.frames[i].frame<<','<<wall<<','<<gpu<<','<<pre<<','<<post<<'\n';
        }
    }
    return 0;
}catch(std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
