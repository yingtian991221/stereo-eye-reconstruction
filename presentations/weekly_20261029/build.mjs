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
const DECODE_BUDGET_MS=2;
const measured=JSON.parse(await fs.readFile(path.join(ROOT,'results/fov_scales_full_20261029/scale_results.json'),'utf8'));
const rows=measured.levels;
if(measured.frames!==1068 || measured.power_w!==30 || measured.warmup_per_frame!==3 || measured.repeats_per_frame!==5 || measured.full_reference_level!=='240x135')throw new Error('Unexpected experiment scope');
const levels=['96x54','240x135','480x270']; // Presentation subset; four measured levels remain in source JSON.
const expectedScales=[0.1,0.25,0.5];
if(!Array.isArray(rows)||rows.length!==4)throw new Error('Expected four completed scale groups');
const get=l=>rows.find(r=>r.level===l);
levels.forEach((l,i)=>{
 const r=get(l);
 if(!r || r.frames!==1068 || r.timing_samples!==5340 || r.quality_samples!==1068 || Number(r.linear_scale)!==expectedScales[i] || Number(r.decode_budget_ms)!==DECODE_BUDGET_MS)throw new Error('Invalid scale group '+l);
 for(const key of ['gpu_mean_ms','wall_mean_ms','total_gpu_mean_ms','full_total_gpu_mean_ms','speedup_total','legacy_delta_db','derived_stereo_delta_db'])if(!Number.isFinite(Number(r[key])))throw new Error('Invalid '+key);
 if(Math.abs(Number(r.total_gpu_mean_ms)-Number(r.gpu_mean_ms)-DECODE_BUDGET_MS)>1e-7)throw new Error('Budget mismatch');
});
const recon=(l,m='fov')=>m==='full'?Number(get(l).full_total_gpu_mean_ms)-DECODE_BUDGET_MS:Number(get(l).gpu_mean_ms);
const budgetMean=(l,m='fov')=>m==='full'?Number(get(l).full_total_gpu_mean_ms):Number(get(l).total_gpu_mean_ms);
const region=l=>String(get(l).linear_scale)+'×';
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
const src='Source: results/fov_scales_full_20261029/scale_results.json and README.md. Same 30W CUDA C++ run: 1068 valid forward odd frames, 3 warmups, 5 timed repetitions per frame, one quality output per configuration/frame. Resident whole-pipeline GPU event timing without internal stage markers, fast resampling, dynamic clocks. This differs from the previous small-sample staged experiment.';

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
 text(s,'More time',80,245,300,58,39,C.blue,true);arrow(s,370,263,145,25,C.blue);
 box(s,700,159,360,202.5,C.light,C.gray);box(s,754,189.375,252,141.75,C.white,C.blue);
 text(s,'Larger full-resolution region',90,323,530,40,28,C.blue,true);
 text(s,'Less time',80,473,300,58,39,C.teal,true);arrow(s,370,491,145,25,C.teal);
 box(s,700,405,360,202.5,C.light,C.gray);box(s,826,475.875,108,60.75,C.white,C.teal);
 text(s,'Smaller full-resolution region',90,551,530,40,28,C.teal,true);
 note(s,'Proposed adaptation. Fixed-center levels are measured; scheduling and deadline-miss reduction remain unverified.');
}
// 4: reconstruction editable diagram
{
 const s=slide('Half-resolution base with a full-resolution center',src+' Mechanism: half-resolution base + padded full-resolution ROI + feather overlay. The full output is 960x540 (1.0x). Region scale is ROI width divided by full-image width: 96x54 => 0.1x, 240x135 => 0.25x, 480x270 => 0.5x. The measured 0.75x level remains in the source dataset but is omitted from this presentation. Width and height both follow these scales. ROI extent scale is not sampling resolution: pixels within the ROI remain full-resolution. The base samples at 0.5x width and 0.5x height (480x270) while covering the entire image.');
 text(s,'Shared image, disparity, and optical-flow inputs',64,151,1100,44,30);
 box(s,90,248,320,180,C.light,C.blue);text(s,'Base sampling\n0.5× width\n0.5× height',112,280,280,112,26,C.blue,true);
 text(s,'Base covers the whole image',90,447,370,36,25,C.muted);
 box(s,485,248,320,180,C.white,C.gray);box(s,590,304,110,68,C.light,C.teal);text(s,'ROI',588,326,150,35,24,C.teal,true);
 text(s,'+',432,307,45,60,42,C.blue,true);text(s,'Full resolution within the ROI',485,447,370,36,25,C.muted);
 arrow(s,826,322,60,22,C.teal);box(s,910,248,300,180,C.light,C.blue);box(s,1015,304,90,68,C.white,C.teal);text(s,'Upsample + blend',920,462,290,40,28,C.blue,true);
 text(s,'1.0× output',943,510,285,40,26,C.muted);
 text(s,'Full-resolution region width: 0.1×, 0.25×, 0.5×',64,552,1140,40,29,C.ink,true);
 note(s,'Region scale = region width / image width. Sampling inside the region stays at full resolution.');
}
// 6: native stacked chart, new 30W CUDA C++ timing
{
 const s=slide('30W CUDA C++: decode budget + reconstruction',src+' Arithmetic means of all 5340 recorded resident whole-pipeline GPU timings per configuration, not wall time. No internal stage markers. Full uses the paired baseline from the 0.25x configuration. Fixed decode budget is 2 ms once per frame, not measured joint RGB/depth/flow decoding or measured end-to-end timing. No input/output copies, network or display. Savings may include reduced clearing and resampling work; no optimal Full baseline claim.');
 const reconstruction=[Number(measured.full_reference.gpu_mean_ms),...levels.map(l=>recon(l))];
 const chart=s.charts.add('bar',{position:{left:64,top:192,width:810,height:394},categories:['Full',...levels.map(region)],series:[{name:'Measured reconstruction',values:reconstruction.map(v=>Number(fixed(v))),fill:C.blue},{name:'Fixed decode budget (2 ms)',values:reconstruction.map(()=>DECODE_BUDGET_MS),fill:C.orange}],barOptions:{direction:'column',grouping:'stacked',gapWidth:75,overlap:100},hasLegend:true,legend:{position:'bottom',textStyle:{fontSize:20}},xAxis:{textStyle:{fontSize:21}},yAxis:{min:0,max:12,majorUnit:2,title:{text:'Decode + GPU reconstruction (ms)',textStyle:{fontSize:22}},textStyle:{fontSize:20},majorGridlines:{fill:C.gray,width:1}},chartFill:C.white,plotAreaFill:C.white});
 applyPresentationChartFont(chart,{fontFamily:FONT});
 text(s,'1068 frames at 30W; 5 repetitions/frame. GPU timing, not wall time.',64,145,1145,35,25,C.blue,true);
 text(s,'0.25× region',930,213,280,50,35,C.blue,true);text(s,fixed(budgetMean('240x135'))+' ms',930,283,300,65,45,C.ink,true);text(s,'decode + reconstruction',905,352,310,40,23,C.muted);
 text(s,(budgetMean('240x135','full')/budgetMean('240x135')).toFixed(2)+'×',930,422,280,62,46,C.teal,true);text(s,'versus Full + decode',930,490,280,40,25,C.muted);
 note(s,'Derived budget, not measured end-to-end. Copies excluded. Includes clearing and resampling; no optimal-Full claim.');
}
// 7: quality native table
{
 const s=slide('Quality and timing across region sizes',src+' Original uint8-overflow PSNR preserved. Stereo delta is derived only if left eye remains unchanged and per-eye PSNR dB is averaged. Quality and timing use the same 30W 1068-frame experiment: 3 warmups and 5 timing samples per frame, one quality output per configuration/frame. Timing is never divided by two. Latency adds a fixed 2 ms per-frame decode budget once, not measured decoding or end-to-end latency. Source: results/fov_scales_full_20261029/scale_results.json.');
 table(s,[['Region width scale','Decode + recon mean','Stereo PSNR loss (dB)'],...levels.map(l=>{const r=get(l);return [region(l),`${fixed(budgetMean(l))} ms`,delta(-Number(r.derived_stereo_delta_db))]})],64,170,1152,337,[340,390,422],27);
 text(s,'Loss versus Full. Derived assuming unchanged left eye and mean per-eye PSNR in dB.',64,537,1150,40,25,C.blue,true);
 text(s,'Original overflow PSNR preserved. Quality and timing: same 30W run, 1068 frames.',64,581,1150,36,23,C.muted);
 note(s,'Timing adds a fixed 2 ms decode budget; not measured end-to-end.');

}
// 8: next verification
{
 const s=slide('Next: measure deadline behavior under jitter','Proposed future work; no measured jitter trace or deadline-miss reduction exists in the current experiment. Slides 5–6 add a fixed 2 ms decode budget to local reconstruction means. Other timing values are local reconstruction measurements. None are measured end-to-end VR results.');
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
const result=await finalizePresentation({workspaceDir:ROOT,candidatePath:candidate,finalPath:FINAL,pythonExecutable:RUNTIME+'/python/python.exe',integrityValidatorPath:SKILL+'/container_tools/inspect_presentation_package_integrity.py',layoutValidatorPath:SKILL+'/container_tools/inspect_presentation_layout_geometry.py',layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit','--require-native-table-slide','6'],explicitTotalSlideCount:7,requiredNativeTableOwnerSlides:[6],requiredNativeChartOwnerSlides:[5],materializeLiteralChartWorkbooks:true,fontPolicy:{basis:'design',families:[FONT]},verifyArtifactToolImport:true,receiptPath:path.join(BUILD,path.basename(FINAL)+'.validation.json')});
console.log(JSON.stringify(result,null,2));
