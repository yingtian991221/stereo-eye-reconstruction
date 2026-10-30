import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
const ROOT=process.cwd();
const RUNTIME='C:/Users/yingt/.cache/codex-runtimes/codex-primary-runtime/dependencies';
process.env.RUNTIME_NODE_MODULES ??= RUNTIME+'/node/node_modules';
const SKILL='C:/Users/yingt/.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11618/skills/presentations';
const {Presentation,PresentationFile}=await import(pathToFileURL(RUNTIME+'/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs'));
const {finalizePresentation,applyPresentationChartFont}=await import(pathToFileURL(SKILL+'/container_tools/artifact_tool_utils.mjs'));
const BUILD=path.join(ROOT,'tmp/weekly_ppt_build');
const OUT=path.join(ROOT,'presentations/weekly_20261029');
await fs.mkdir(BUILD,{recursive:true}); await fs.mkdir(OUT,{recursive:true});
const FONT='Arial';
const C={ink:'#152D43',muted:'#536675',blue:'#086B93',teal:'#148B83',light:'#EAF3F6',orange:'#D17B28',gray:'#D7DFE5',white:'#FFFFFF'};
const p=Presentation.create({slideSize:{width:1280,height:720}});
const csv=await fs.readFile(path.join(ROOT,'results/fov_levels_xavier_full_20261027/overview.csv'),'utf8');
const lines=csv.trim().split(/\r?\n/).map(x=>x.split(','));const data=lines.slice(1).map(row=>Object.fromEntries(lines[0].map((k,i)=>[k,row[i]])));
const levels=['80x46','160x90','320x180','480x270','640x360'];
const get=(l,t='resident',m='fov')=>data.find(r=>r.level===l&&r.timing===t&&r.mode===m);
const means=JSON.parse(await fs.readFile(path.join(OUT,'mean_timings.json'),'utf8'));
const mean=(l,t='resident',m='fov')=>{
 const row=means.cuda.find(r=>r.level===l&&r.timing===t&&r.mode===m);
 if(!row || row.samples!==5340)throw new Error('Incomplete mean timing group');
 return row.wall_mean_ms;
};
const DECODE_BUDGET_MS=2; // Fixed per-frame budget, added once; not measured joint decoding.
const budgetMean=(l,t='resident',m='fov')=>DECODE_BUDGET_MS+mean(l,t,m);
const region=l=>(means.cuda.find(r=>r.level===l).region_percent).toFixed(1)+'%';
const fixed=n=>Number(n).toFixed(3), delta=n=>Number(n).toFixed(4);
function text(s,txt,x,y,w,h,size=27,color=C.ink,bold=false){
 const sh=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 sh.text=txt.split('\n').map(t=>({runs:[{run:t,style:{typeface:FONT,fontSize:`${size}px`,bold,color}}]}));
 sh.text.insets=0; return sh;
}
function box(s,x,y,w,h,fill=C.light,stroke=C.blue){return s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:stroke,width:1.5}})}
function line(s,x,y,w,h,color=C.gray,width=2){return s.shapes.add({geometry:'line',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:color,width}})}
function arrow(s,x,y,w,h=15,color=C.blue){return s.shapes.add({geometry:'rightArrow',position:{left:x,top:y,width:w,height:h},fill:color,line:{fill:color,width:0}})}
function slide(title,notes='') {const s=p.slides.add();s.background.fill=C.white; text(s,title,64,40,1145,66,42,C.ink,true);line(s,64,122,1152,0,C.gray,1); text(s,String(p.slides.items.length),1192,675,30,24,17,C.muted);s.speakerNotes.text=notes;return s;}
function note(s,txt){text(s,txt,64,622,1125,48,20,C.muted);}
function table(s,values,x,y,width,height,widths,size=25){
 const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width,height,columnWidths:widths,values});
 for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){
  const cell=t.getCell(r,c);cell.fill=r===0?C.ink:(r%2?C.white:C.light);
  cell.text.set([{runs:[{run:String(values[r][c]),style:{typeface:FONT,fontSize:`${size}px`,color:r===0?C.white:C.ink,bold:r===0}}]}]);
 }
 t.borders.assign({fill:C.gray,width:1,style:'solid'});return t;
}
const src='Source: results/fov_levels_xavier_full_20261027/README.md; overview.csv; summary.csv. Commit 0f1506c. Date 2026-10-27. Raw evidence: evidence.tar.gz.';

// 1: minimal cover
{
 const s=p.slides.add();s.background.fill=C.white;
 text(s,'Deadline-aware\nFoveated Reconstruction',72,132,1100,172,62,C.ink,true);
 text(s,'Research weekly update',76,346,1120,50,31,C.blue);
 text(s,'Network jitter, reconstruction design, and Xavier measurements',76,448,1100,52,29,C.muted);
 text(s,'2026-10-29',76,614,1000,35,25,C.muted);
 s.speakerNotes.text='Weekly update. This deck distinguishes the proposed deadline scheduler from the implemented fixed-center FOV sweep. No measured network jitter or deadline-miss improvement is claimed.';
}
// 2: requested editable timing schematic
{
 const s=slide('Jitter reduces the reconstruction budget','Schematic only, not measured data. 90 FPS gives a frame period of 1000/90=11.11 ms. Frame period is not an established end-to-end deadline. The bars illustrate arrival/decode variability relative to a chosen display deadline.');
 text(s,'Later input readiness leaves less time before the display deadline',64,153,1140,48,30);
 const x=262,end=1140;
 const rows=[['Early arrival',220,C.teal],['Typical arrival',410,C.blue],['Late arrival',620,C.orange]];
 rows.forEach(([label,offset,color],i)=>{const y=260+i*100; text(s,label,65,y+5,180,44,28);box(s,x,y,offset,46,C.gray,C.gray);box(s,x+offset,y,end-x-offset-80,46,C.light,color);box(s,end-80,y,80,46,'#FAEDD9',C.orange);text(s,'Budget',x+offset+16,y+8,end-x-offset-20,35,23,color,true);line(s,x+offset,y-16,0,74,color,3);});
 line(s,end,228,0,304,C.orange,3);text(s,'Deadline D',1020,199,205,37,25,C.orange,true);
 text(s,'Display reserve',1055,539,160,28,20,C.orange);text(s,'Transfer + decode',280,567,300,36,25,C.muted);text(s,'B = D − t_ready − T_display − margin',600,567,610,40,28,C.blue,true);
 note(s,'Schematic, not a measured jitter trace. A 90 FPS frame period is 11.11 ms, not a validated end-to-end deadline.');
}
// 3: mechanism and status
{
 const s=slide('Adapt the full-resolution region to available time','Proposed adaptive mechanism, not implemented/validated. After inputs are ready, more remaining reconstruction time allows a larger full-resolution region; less time calls for a smaller region. The half-resolution base still covers the full image. Region sizes in this schematic are illustrative, not quantitative. Current implementation covers a fixed-center FOV sweep and latency profiles.');
 text(s,'More time',64,233,350,58,39,C.blue,true);arrow(s,340,248,140,25,C.blue);
 box(s,535,180,650,155,C.light,C.gray);box(s,670,200,380,115,C.white,C.blue);
 text(s,'Larger full-resolution region',646,350,555,45,29,C.blue,true);
 text(s,'Less time',64,446,350,58,39,C.teal,true);arrow(s,340,461,140,25,C.teal);
 box(s,535,405,650,155,C.light,C.gray);box(s,805,452,110,62,C.white,C.teal);
 text(s,'Smaller full-resolution region',625,575,580,40,29,C.teal,true);
 note(s,'Proposed adaptation. Fixed-center levels are measured; scheduling and deadline-miss reduction remain unverified.');
}
// 4: reconstruction editable diagram
{
 const s=slide('Half-resolution base with a full-resolution center',src+' Mechanism: half-resolution base + padded full-resolution ROI + feather overlay. Region percentages are spatial coverage of a 960x540 image: 80x46=0.7098765%, 160x90=2.7777778%, 320x180=11.1111111%, 480x270=25%, 640x360=44.4444444%. The base samples at 50% width and 50% height, giving 25% as many pixels (480x270), while covering the entire image. Region coverage and sampling resolution are different quantities.');
 text(s,'Shared image, disparity, and optical-flow inputs',64,151,1100,44,30);
 box(s,90,248,320,180,C.light,C.blue);text(s,'Base sampling\n50% W × 50% H\n(25% of pixels)',112,280,280,112,26,C.blue,true);
 text(s,'Base covers the whole image',90,447,370,36,25,C.muted);
 box(s,485,248,320,180,C.white,C.gray);box(s,590,304,110,68,C.light,C.teal);text(s,'ROI',588,326,150,35,24,C.teal,true);
 text(s,'+',432,307,45,60,42,C.blue,true);text(s,'Full resolution within the ROI',485,447,370,36,25,C.muted);
 arrow(s,826,322,60,22,C.teal);box(s,910,248,300,180,C.light,C.blue);box(s,1015,304,90,68,C.white,C.teal);text(s,'Upsample + blend',920,462,290,40,28,C.blue,true);
 text(s,'960 × 540 output',943,510,285,40,26,C.muted);
 text(s,'Full-resolution region: 0.7%, 2.8%, 11.1%, 25.0%, 44.4% of image',64,552,1140,40,29,C.ink,true);
 note(s,'Region % means image-area coverage; base sampling is separate. Fixed center, 3 px halo; no eye tracking.');
}
// 5: coverage and timing
{
 const s=slide('Coverage and measurement scope',src+' Measured timing excludes decoding. Slides 6 and 7 add one fixed 2 ms decoding budget per frame to measured means; derived budget totals are not measured end-to-end latency. No joint RGB, depth and flow decoding measurement is claimed.');
 table(s,[['Forward sequence','Frames','Right-eye frame IDs'],['15 mm / 300','147','Odd frames 7–299'],['15 mm / 800','387','Odd frames 7–779'],['35 mm / 300','147','Odd frames 7–299'],['35 mm / 800','387','Odd frames 7–779']],64,167,660,330,[240,140,280],24);
 text(s,'1068 frames',796,172,360,70,48,C.blue,true);
 text(s,'Xavier 15W Desktop\nCUDA 11.4, unlocked clocks\n3 warmups + 5 timed runs/frame\nOne quality output/config/frame',796,268,400,192,26);
 text(s,'Resident: GPU-resident inputs, reconstruction, upsampling, and blending\nStream: also includes input upload and output download\nSlides 6–7 add a fixed 2 ms/frame decode budget; not measured end-to-end.',64,515,1135,99,24,C.ink);
 note(s,'Excludes backward scenes, even frames, and unsupported tail frames. Timing excludes I/O, allocation, network, decoding, and display.');
}
// 6: native chart
{
 const s=slide('Decode budget + reconstruction across FOV levels',src+' Arithmetic means of all 5340 timing samples in each level/timing/mode group, computed by compute_means.py into mean_timings.json. No sample trimming. Full baseline measured separately per level. Fast resample enabled. Each value covers all 1068 supported frames. Adds a fixed 2 ms decode budget once per frame. Speedup is (2 + mean(full resident))/(2 + mean(FOV resident)) at the same region level. This is a derived budget, not measured end-to-end timing or measured joint RGB/depth/flow decoding. See results/fov_decode_budget_2ms_20261029/README.md and summary.csv. Region labels are image-area coverage, not sampling resolution.');
 const chart=s.charts.add('bar',{position:{left:64,top:176,width:810,height:410},categories:levels.map(region),series:[{name:'FOV resident + decode',values:levels.map(l=>Number(fixed(budgetMean(l)))),fill:C.blue},{name:'FOV stream + decode',values:levels.map(l=>Number(fixed(budgetMean(l,'stream')))),fill:C.orange},{name:'Full resident + decode',values:levels.map(l=>Number(fixed(budgetMean(l,'resident','full')))),fill:C.muted}],barOptions:{direction:'column',grouping:'clustered',gapWidth:75,overlap:0},hasLegend:true,legend:{position:'bottom',textStyle:{fontSize:18}},xAxis:{textStyle:{fontSize:21}},yAxis:{min:0,max:16,majorUnit:2,title:{text:'Decode + recon mean (ms)',textStyle:{fontSize:22}},textStyle:{fontSize:20},majorGridlines:{fill:C.gray,width:1}},chartFill:C.white,plotAreaFill:C.white});
 applyPresentationChartFont(chart,{fontFamily:FONT});
 text(s,'2.8% region',930,202,280,50,35,C.blue,true);text(s,fixed(budgetMean('160x90'))+' ms',930,275,300,65,45,C.ink,true);text(s,'decode + resident',930,347,280,40,25,C.muted);
 text(s,(budgetMean('160x90','resident','full')/budgetMean('160x90')).toFixed(2)+'×',930,417,280,62,46,C.teal,true);text(s,'versus full + decode',930,485,280,40,25,C.muted);
 text(s,'Fixed decode budget: 2 ms/frame + measured reconstruction; stream also includes copies.',64,145,1145,31,23,C.blue,true);
 note(s,'Derived budget, not measured end-to-end. Fast resampling enabled; gains also include upsampling changes. No optimal-baseline claim.');
}
// 7: quality native table
{
 const s=slide('Quality–latency trade-off',src+' Original uint8-overflow PSNR preserved. Stereo delta is derived only if left eye remains unchanged and per-eye PSNR dB is averaged. Timing is never divided by two. Latency adds a fixed 2 ms per-frame decode budget once, not measured decoding or end-to-end latency. Source: results/fov_decode_budget_2ms_20261029/summary.csv.');
 table(s,[['Region (% of image)','Decode + recon mean','Right-eye ΔPSNR','Stereo mean ΔPSNR*'],...levels.map(l=>{const r=get(l);return [region(l),`${fixed(budgetMean(l))} ms`,`${delta(r.legacy_delta_vs_full_db)} dB`,`${delta(Number(r.legacy_delta_vs_full_db)/2)} dB`]})],64,170,1152,337,[265,275,286,326],24);
 text(s,'* Unchanged left eye, mean per-eye PSNR in dB: stereo difference = right-eye difference / 2',64,537,1150,40,25,C.blue,true);
 text(s,'ΔPSNR = FOV − full, using original overflow PSNR. Standard PSNR can show a different trend.',64,581,1150,36,23,C.muted);
 note(s,'Fixed 2 ms decode budget + resident reconstruction. Stereo values derived; non-atomic writes remain. No SSIM/LPIPS.');
}
// 8: Numba compatible proof
{
 const n=JSON.parse(await fs.readFile(path.join(ROOT,'results/numba_xavier_20261029/mode7_15w/result.json'),'utf8'));
 if (process.env.NUMBA30_RESULT) {
 const thirty=JSON.parse(await fs.readFile(path.resolve(ROOT,process.env.NUMBA30_RESULT),'utf8'));
 const keys=Object.keys(n.workloads);
 if(keys.length!==4 || thirty.frame!==39 || thirty.repeats!==100 || !keys.every(k=>thirty.workloads[k])) throw new Error('Unmatched 30W coverage');
 const s=slide('Numba latency at 15W and 30W','Sources: results/numba_xavier_20261029/mode7_15w/result.json and '+process.env.NUMBA30_RESULT+'. Arithmetic means from mean_timings.json of all 100 samples per method, four workloads, frame39 only. 15W was measured before 30W. No confidence intervals. Some startup drift remains. Same Numba implementation and inputs. Preallocated resident timing includes launch/synchronization; excludes JIT, allocation, transfers, I/O. Power modes: 15W Desktop mode7 and 30W 4CORE mode5. Dynamic clocks, same four CPU cores. The 30W mode raises GPU/EMC limits but lowers the CPU maximum. Original generate_right includes allocation/transfer and startup drift; it is not the resident path shown. Numba upsampling differs from optimized CUDA C++.');
 const rows=keys.map(k=>{const a=means.numba.mode7_15w[k],b=means.numba.mode5_30w[k];return[k.replace('driving_',''),fixed(a.full),fixed(b.full),fixed(a['160x90']),fixed(b['160x90'])];});
 table(s,[['Sequence','Full 15W','Full 30W','ROI 15W','ROI 30W'],...rows],64,180,1152,285,[232,230,230,230,230],26);
 text(s,'Frame 39 per sequence, 100 repeats. Reconstruction means (ms); no decode. Region = 2.8%.',64,495,1152,40,26,C.blue,true);
 text(s,'30W 4-core mode raises the GPU cap but lowers the CPU cap versus 15W Desktop.\nDynamic clocks. Numba and optimized C++ use different upsampling implementations.',64,550,1152,72,25);
 note(s,'Small-sample power-mode comparison, not a complete-dataset study or a language-only comparison.');
 } else {
 const s=slide('Numba runs on Xavier: a small-sample check','Source: results/numba_xavier_20261029/mode7_15w/result.json, environment.txt, run.log. Arithmetic means from mean_timings.json of 100 timing samples per method, four workloads, frame39 only. No confidence intervals. Numba0.58.1/Python3.8/CUDA11.4. Original source-function calls include allocations/transfers/debug copies and show warmup drift; not directly comparable to resident timing.');
 const rows=Object.keys(n.workloads).map(k=>{const r=means.numba.mode7_15w[k];return[k.replace('driving_',''),fixed(r.full),fixed(r['160x90']),fixed(r['320x180'])];});
 table(s,[['Sequence','Full (ms)','Region 2.8%','Region 11.1%'],...rows],64,180,1152,285,[280,280,296,296],26);
 text(s,'15W. Frame 39 per sequence, 100 repeats. Resident reconstruction means; no decode.',64,495,1152,40,26,C.blue,true);
 text(s,'Numba 0.58.1 + Python 3.8: real GPU JIT and execution passed.\nIts upsampler differs from optimized CUDA C++; this is not a language-only comparison.',64,550,1152,72,25);
 note(s,'Original generate_right also runs with allocation/transfer and startup drift. See the companion deck for 30W.');
 }
}
// 9: next verification
{
 const s=slide('Next: measure deadline behavior under jitter','Proposed future work; no measured jitter trace or deadline-miss reduction exists in the current experiment. Slides 6–7 add a fixed 2 ms decode budget to local reconstruction means. Other timing values are local reconstruction measurements. None are measured end-to-end VR results.');
 const ys=[179,315,451];
 const titles=['Record the actual per-frame budget','Implement budget-based ROI selection','Compare fixed and adaptive policies on the same trace'];
 const bodies=['Log arrival, decode completion, and display deadline. Reserve display time and a margin.','Build a percentile-based profile. Define a fallback when no level fits the budget.','Report deadline-miss rate, tail latency, and quality. Repeat runs to check stability.'];
 titles.forEach((t,i)=>{text(s,`${i+1}`,66,ys[i],60,60,40,C.blue,true);text(s,t,140,ys[i],1050,48,32,C.ink,true);text(s,bodies[i],140,ys[i]+57,1045,48,27,C.muted);});
 note(s,'Measured: fixed-center quality–latency levels. Adaptive scheduling and benefits under jitter still require validation.');
}

for(let i=0;i<p.slides.items.length;i++){
 const blob=await p.export({slide:p.slides.items[i],format:'png',scale:1});
 await fs.writeFile(path.join(BUILD,`slide-${i+1}.png`),new Uint8Array(await blob.arrayBuffer()));
}
const candidate=path.join(BUILD,'candidate.pptx');await(await PresentationFile.exportPptx(p)).save(candidate);
const FINAL=path.join(OUT,process.env.PPTX_NAME || 'weekly_20261029_english_final.pptx');
const result=await finalizePresentation({workspaceDir:ROOT,candidatePath:candidate,finalPath:FINAL,pythonExecutable:RUNTIME+'/python/python.exe',integrityValidatorPath:SKILL+'/container_tools/inspect_presentation_package_integrity.py',layoutValidatorPath:SKILL+'/container_tools/inspect_presentation_layout_geometry.py',layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit','--require-native-table-slide','5','--require-native-table-slide','7','--require-native-table-slide','8'],explicitTotalSlideCount:9,requiredNativeTableOwnerSlides:[5,7,8],requiredNativeChartOwnerSlides:[6],materializeLiteralChartWorkbooks:true,fontPolicy:{basis:'design',families:[FONT]},verifyArtifactToolImport:true,receiptPath:path.join(BUILD,path.basename(FINAL)+'.validation.json')});
console.log(JSON.stringify(result,null,2));
