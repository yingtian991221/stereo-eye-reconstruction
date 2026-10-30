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
 const s=slide('Budget-based reconstruction selection','Proposed scheduler, not implemented/validated. t_ready denotes decoded reconstruction inputs ready. T_display and safety margin must be measured/reserved. Current implementation covers fixed-center ROI reconstruction and latency profiles.');
 const xs=[64,296,528,760,992],w=204,y=228;
 const labels=['Inputs ready\n(after decode)','Estimate\nbudget B','Latency profile\nROI selection','Reconstruct\nand blend','Submit\nfor display'];
 labels.forEach((label,i)=>{box(s,xs[i],y,w,128,i===3?C.light:C.white,i===3?C.teal:C.blue);text(s,label,xs[i]+14,y+28,w-28,90,25,C.ink,true);if(i<4)arrow(s,xs[i]+w+4,y+54,23,18);});
 text(s,'Proposed rule',64,421,210,45,29,C.blue,true);
 text(s,'Choose the highest-quality level with T̂(level) ≤ B',280,421,925,48,32,C.ink,true);
 text(s,'Use a conservative latency percentile. Validate prediction error and margin.',280,480,925,46,27,C.muted);
 note(s,'Implemented: fixed-center FOV sweep and latency profiles. Dynamic scheduling and deadline-miss reduction remain unverified.');
}
// 4: reconstruction editable diagram
{
 const s=slide('Half-resolution base with a full-resolution center',src+' Mechanism reflects current half base + padded full-resolution ROI + feather overlay. ROI dimensions are pixels, not angles.');
 text(s,'Shared image, disparity, and optical-flow inputs',64,151,1100,44,30);
 box(s,90,248,320,180,C.light,C.blue);text(s,'Full-image base\n480 × 270',142,290,235,80,28,C.blue,true);
 text(s,'Half resolution in the periphery',90,447,370,36,25,C.muted);
 box(s,485,248,320,180,C.white,C.gray);box(s,590,304,110,68,C.light,C.teal);text(s,'ROI',588,326,150,35,24,C.teal,true);
 text(s,'+',432,307,45,60,42,C.blue,true);text(s,'Full resolution within the ROI',485,447,370,36,25,C.muted);
 arrow(s,826,322,60,22,C.teal);box(s,910,248,300,180,C.light,C.blue);box(s,1015,304,90,68,C.white,C.teal);text(s,'Upsample + blend',920,462,290,40,28,C.blue,true);
 text(s,'960 × 540 output',943,510,285,40,26,C.muted);
 text(s,'ROI sizes: 80×46, 160×90, 320×180, 480×270, 640×360',64,552,1140,40,29,C.ink,true);
 note(s,'Fixed center, 3 px halo, and edge blending. Diagram not to scale. Eye tracking is not integrated.');
}
// 5: coverage and timing
{
 const s=slide('Coverage and measurement scope',src);
 table(s,[['Forward sequence','Frames','Right-eye frame IDs'],['15 mm / 300','147','Odd frames 7–299'],['15 mm / 800','387','Odd frames 7–779'],['35 mm / 300','147','Odd frames 7–299'],['35 mm / 800','387','Odd frames 7–779']],64,167,660,330,[240,140,280],24);
 text(s,'1068 frames',796,172,360,70,48,C.blue,true);
 text(s,'Xavier 15W Desktop\nCUDA 11.4, unlocked clocks\n3 warmups + 5 timed runs/frame\nOne quality output/config/frame',796,268,400,192,26);
 text(s,'Resident: GPU-resident inputs, reconstruction, upsampling, and blending\nStream: also includes input upload and output download',64,526,1135,78,27,C.ink);
 note(s,'Excludes backward scenes, even frames, and unsupported tail frames. Timing excludes I/O, allocation, network, decoding, and display.');
}
// 6: native chart
{
 const s=slide('Smaller ROIs reduce reconstruction latency',src+' Chart uses pooled timing medians. Full baseline is separately measured per level. Fast resample enabled. Each series value corresponds to all 1068 supported frames.');
 const chart=s.charts.add('line',{position:{left:64,top:176,width:810,height:410},categories:levels.map(v=>v.replace('x','×')),series:[{name:'FOV resident',values:levels.map(l=>Number(fixed(get(l).wall_p50_ms))),fill:C.blue},{name:'FOV stream',values:levels.map(l=>Number(fixed(get(l,'stream').wall_p50_ms))),fill:C.orange},{name:'Full resident',values:levels.map(l=>Number(fixed(get(l,'resident','full').wall_p50_ms))),fill:C.muted}],hasLegend:true,legend:{position:'bottom',textStyle:{fontSize:22}},xAxis:{textStyle:{fontSize:21}},yAxis:{min:0,max:14,majorUnit:2,title:{text:'p50 latency (ms)',textStyle:{fontSize:22}},textStyle:{fontSize:20},majorGridlines:{fill:C.gray,width:1}},chartFill:C.white,plotAreaFill:C.white});
 applyPresentationChartFont(chart,{fontFamily:FONT});
 text(s,'160 × 90',930,202,280,50,35,C.blue,true);text(s,'4.637 ms',930,275,300,65,45,C.ink,true);text(s,'resident p50',930,347,280,40,25,C.muted);
 text(s,'2.32×',930,417,280,62,46,C.teal,true);text(s,'versus measured full',930,485,280,40,25,C.muted);
 note(s,'Fast resampling enabled. Cross-implementation gains also include upsampling changes, not only FOV. No claim of an optimal full baseline.');
}
// 7: quality native table
{
 const s=slide('Quality–latency trade-off',src+' Original uint8-overflow PSNR preserved. Stereo delta is derived only if left eye remains unchanged and per-eye PSNR dB is averaged. Timing is never divided by two.');
 table(s,[['ROI','resident p50 / p95','Right-eye ΔPSNR','Stereo mean ΔPSNR*'],...levels.map(l=>{const r=get(l);return [l.replace('x','×'),`${fixed(r.wall_p50_ms)} / ${fixed(r.wall_p95_ms)} ms`,`${delta(r.legacy_delta_vs_full_db)} dB`,`${delta(Number(r.legacy_delta_vs_full_db)/2)} dB`]})],64,170,1152,337,[195,345,286,326],24);
 text(s,'* Unchanged left eye, mean per-eye PSNR in dB: stereo difference = right-eye difference / 2',64,537,1150,40,25,C.blue,true);
 text(s,'ΔPSNR = FOV − full, using original overflow PSNR. Standard PSNR can show a different trend.',64,581,1150,36,23,C.muted);
 note(s,'Stereo values are derived; latency is not halved. Non-atomic writes remain. SSIM/LPIPS are not measured.');
}
// 8: Numba compatible proof
{
 const s=slide('Numba runs on Xavier: a small-sample check','Source: results/numba_xavier_20261029/mode7_15w/result.json, environment.txt, run.log. Four workloads, frame39 only, 100 timing samples per method, Numba0.58.1/Python3.8/CUDA11.4. Original source-function calls include allocations/transfers/debug copies and show warmup drift; not directly comparable to resident timing.');
 const n=JSON.parse(await fs.readFile(path.join(ROOT,'results/numba_xavier_20261029/mode7_15w/result.json'),'utf8'));
 const rows=Object.entries(n.workloads).map(([k,r])=>[k.replace('driving_',''),fixed(r.fov_pilot.full.p50_ms),fixed(r.fov_pilot.rois['160x90'].half_base_plus_roi.p50_ms),fixed(r.fov_pilot.rois['320x180'].half_base_plus_roi.p50_ms)]);
 table(s,[['Sequence','Full (ms)','ROI 160×90','ROI 320×180'],...rows],64,180,1152,285,[280,280,296,296],26);
 text(s,'15W. Frame 39 per sequence, 100 repeats. Preallocated resident-path p50.',64,495,1152,40,26,C.blue,true);
 text(s,'Numba 0.58.1 + Python 3.8: real GPU JIT and execution passed.\nIts upsampler differs from optimized CUDA C++; this is not a language-only comparison.',64,550,1152,72,25);
 note(s,'Original generate_right also runs, with allocation/transfer and startup drift. 30W awaits an authenticated power-mode switch.');
}
// 9: next verification
{
 const s=slide('Next: measure deadline behavior under jitter','Proposed future work; no measured jitter trace or deadline-miss reduction exists in the current experiment. All values on earlier slides are local reconstruction measurements, not end-to-end VR results.');
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







