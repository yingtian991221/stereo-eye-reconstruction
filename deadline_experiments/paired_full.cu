// Full-only compatibility control: retain Numba's unused RGB debug-mask writes.
#define main archived_main
#include "../jetson_cuda/pirate_bench.cu"
#undef main
__global__ void matchedClear(Byte*a,Byte*b,Byte*c,Byte*z,Byte*m,Byte*debug,int w,int h){
    int y=blockIdx.x*blockDim.x+threadIdx.x,x=blockIdx.y*blockDim.y+threadIdx.y;
    if(x>=w||y>=h)return;int i=y*w+x;z[i]=m[i]=0;
    for(int k=0;k<3;k++)a[i*3+k]=b[i*3+k]=c[i*3+k]=debug[i*3+k]=0;
}
__global__ void matchedComposite(const Byte*t,Byte*s,Byte*m,Byte*debug,int w,int h){
    int y=blockIdx.x*blockDim.x+threadIdx.x,x=blockIdx.y*blockDim.y+threadIdx.y;
    if(x>=w||y>=h)return;int i=y*w+x;m[i]=0;
    for(int k=0;k<3;k++)debug[3*i+k]=1;
    if(int(s[3*i])+s[3*i+1]+s[3*i+2]==0){
        if(int(t[3*i])+t[3*i+1]+t[3*i+2]==0)m[i]=1;
        for(int k=0;k<3;k++)s[3*i+k]=t[3*i+k];
    }
}
int main(int argc,char**argv){try{
    if(argc!=3)throw std::runtime_error("paired_full packet output.csv");
    auto f=load(argv[1]);Input in(f.w,f.h);in.upload(f);Work w(f.w,f.h);Buffer<Byte> debug(f.w*f.h*3);
    auto run=[&]{matchedClear<<<grid(f.w,f.h),block>>>(w.temporal.p,w.spatial.p,w.out.p,w.z.p,w.mask.p,debug.p,f.w,f.h);
        temporalKernel<<<grid(f.w,f.h),block>>>(in.prev.p,in.flow.p,w.temporal.p,f.w,f.h,f.w,f.h,0,0,f.p);
        disparityKernel<<<grid(f.w,f.h),block>>>(in.left.p,in.depth.p,w.spatial.p,w.z.p,f.w,f.h,f.w,f.h,0,0,f.w,f.p);
        matchedComposite<<<grid(f.w,f.h),block>>>(w.temporal.p,w.spatial.p,w.mask.p,debug.p,f.w,f.h);
        fillKernel<<<grid(f.w,f.h),block>>>(w.spatial.p,w.mask.p,w.out.p,f.w,f.h);};
    for(int i=0;i<20;i++)run();CK(cudaDeviceSynchronize());Event a,b;
    std::ofstream out(argv[2]);out<<"iteration,wall_ms,gpu_ms\n"<<std::setprecision(12);
    for(int i=0;i<50;i++){auto t=std::chrono::steady_clock::now();CK(cudaEventRecord(a.e));run();CK(cudaEventRecord(b.e));CK(cudaEventSynchronize(b.e));double wall=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-t).count();float gpu;CK(cudaEventElapsedTime(&gpu,a.e,b.e));out<<i<<','<<wall<<','<<gpu<<'\n';}
    std::vector<Byte> result(f.w*f.h*3);CK(cudaMemcpy(result.data(),w.out.p,result.size(),cudaMemcpyDeviceToHost));ppm(std::string(argv[2])+".ppm",result,f.w,f.h);
    return 0;
}catch(std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
