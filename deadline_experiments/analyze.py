"""Audit real release/deadline logs, summarize and draw paper-style figures."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from prepare import select

POLICIES=['Full','Half','FOV_0.1','FOV_0.25','FOV_0.5','FOV_0.7','Dynamic_whole','Dynamic_center']
# Blue/green/gold/gray from the supplied Pirate camera-ready PDF, plus dark
# outlines and an accent for the two controllers. Serif publication layout.
COLORS=['#8497B0','#BF9000','#BDD7EE','#9DC3E6','#A9D18E','#548235','#203F50','#C00000']
LABELS=['Full','Half','FoV 0.1','FoV 0.25','FoV 0.5','FoV 0.7','Dynamic (whole)','Dynamic (center)']


def longest_miss(x):
    best=run=0
    for v in x:
        run=run+1 if v else 0;best=max(best,run)
    return best


def analyze(root):
    config=json.loads((root/'config.json').read_text())
    files=sorted((root/'replay').glob('*.csv'))
    if not files: raise ValueError('No measured logs')
    d=pd.concat([pd.read_csv(f) for f in files],ignore_index=True)
    plans=pd.read_csv(root/'release_plan.csv')
    generous=root/'release_plan_generous.csv'
    if generous.exists():plans=pd.concat([plans,pd.read_csv(generous)],ignore_index=True)
    expected=config['rounds']*plans.scenario.nunique()*8*config['count']
    if len(d)!=expected: raise ValueError('Incomplete run: %d / %d rows'%(len(d),expected))
    check=d.merge(plans,on=['scenario','frame'],validate='many_to_one',suffixes=('','_plan'))
    assert np.max(np.abs(check.release_plan_ms-check.release_ms))<1e-6
    assert np.max(np.abs(check.deadline_ms-check.deadline_ms_plan))<1e-6
    assert not d.duplicated(['scenario','policy','round','index']).any()
    assert (d.history_frame==d.frame-1).all()
    assert (d.miss==1-d.accepted).all()
    assert (d.decision_ms>=d.release_actual_ms).all()
    assert (d.start_ms>=d.decision_ms).all()
    assert (d.finish_ms>=d.start_ms).all()
    assert ((d.finish_ms<=d.deadline_ms)&(d.generated==1)).equals(d.accepted.astype(bool))
    assert (d.display_frame<=d.frame).all()
    assert np.max(np.abs(d.margin_ms-(d.deadline_ms-d.finish_ms)))<1e-6
    assert not set(config['profiles_frames']) & set(d.frame)
    estimates=pd.read_csv(root/'estimates.csv').to_dict('records')
    for r in d.itertuples():
        if r.generated:
            expected_config=select(estimates,r.budget_ms,'center_score' if r.policy=='Dynamic_center' else 'whole_score') if r.policy.startswith('Dynamic') else r.policy
            assert r.config==expected_config, (r.frame,r.policy,r.config,expected_config)
        else:
            assert r.budget_ms<=0 and r.config=='Skipped'
    for _,g in d.groupby(['scenario','policy','round']):
        g=g.sort_values('index');assert len(g)==config['count']
        assert np.all(np.diff(g.deadline_ms)>0)
        previous=config['first_frame']-1
        for r in g.itertuples():
            if r.accepted: previous=r.frame
            assert r.display_frame==previous
    def summary(g):
        made=g[g.generated==1];ontime=g[g.accepted==1]
        return pd.Series(dict(frames=len(g),miss_rate=g.miss.mean(),
            mean_remaining_budget_ms=g.budget_ms.mean(),mean_queue_ms=g.queue_ms.mean(),
            mean_release_slip_ms=(g.release_actual_ms-g.release_plan_ms).mean(),
            mean_generated_duration_ms=(made.finish_ms-made.start_ms).mean(),
            mean_margin_ms=made.margin_ms.mean(),
            generated_psnr_db=made.generated_stereo_psnr_db.mean(),
            ontime_psnr_db=ontime.generated_stereo_psnr_db.mean(),
            displayed_psnr_db=g.display_stereo_psnr_db.mean(),
            displayed_center_psnr_db=g.display_center_psnr_db.mean(),
            displayed_mse=g.display_stereo_mse.mean(),displayed_center_mse=g.display_center_mse.mean(),
            displayed_boundary_mse=g.display_boundary_mse.mean(),
            max_consecutive_misses=max(longest_miss(s.sort_values('index').miss) for _,s in g.groupby('round'))))
    grouped=d.groupby(['scenario','policy'],sort=False)
    rows=[]
    for (scenario,policy),g in grouped:
        r=dict(scenario=scenario,policy=policy,**summary(g).to_dict())
        r['planned_budget_ms']=(plans[plans.scenario==scenario].deadline_ms-plans[plans.scenario==scenario].release_ms).mean()
        rows.append(r)
    s=pd.DataFrame(rows);s.to_csv(root/'summary.csv',index=False)
    per_round=[]
    for (scenario,policy,round_),g in d.groupby(['scenario','policy','round']):
        per_round.append(dict(scenario=scenario,policy=policy,round=round_,**summary(g).to_dict()))
    pd.DataFrame(per_round).to_csv(root/'per_round_summary.csv',index=False)
    d.groupby(['scenario','policy','config']).size().rename('frames').to_csv(root/'selections.csv')
    audit=dict(rows=len(d),runs=len(files),profile_eval_disjoint=True,fixed_deadlines_verified=True,
               selection_matches_frozen_profile_and_current_budget=True,
               history_previous_decoded_frame_verified=True,display_id_fallback_verified=True,
               max_release_slip_ms=float((d.release_actual_ms-d.release_plan_ms).max()),
               metric='float-domain MSE; mean per-frame standard stereo PSNR reported',
               synthetic='release schedule and display sequence',measured='host release/start/finish and actual reconstruction output',
               assumed='90Hz playback, 20ms model offset, 1ms submission reserve; no decode measurement')
    if 'warm_gpu_hz' in d:
        audit['pretrial_gpu_hz_range']=[int(d.warm_gpu_hz.min()),int(d.warm_gpu_hz.max())]
    (root/'audit.json').write_text(json.dumps(audit,indent=2))
    plt.rcParams.update({'font.family':'serif','font.serif':['Times New Roman','DejaVu Serif'],
                         'font.size':10,'axes.labelsize':11,'legend.fontsize':8,'pdf.fonttype':42,
                         'axes.spines.top':False,'axes.spines.right':False,'savefig.bbox':'tight'})
    figs=root/'figures';figs.mkdir(exist_ok=True)
    def save(fig,name):
        fig.savefig(figs/(name+'.png'),dpi=180);fig.savefig(figs/(name+'.pdf'));plt.close(fig)
    fig,axs=plt.subplots(1,3,figsize=(12,3.1),constrained_layout=True)
    for i,p in enumerate(POLICIES):
        z=s[(s.policy==p)&s.scenario.str.startswith('budget')].sort_values('planned_budget_ms')
        for ax,col in zip(axs,['miss_rate','displayed_psnr_db','mean_margin_ms']):
            ax.plot(z.planned_budget_ms,z[col]*(100 if col=='miss_rate' else 1),'-o',color=COLORS[i],label=LABELS[i],ms=3,lw=1.5)
    for ax,y in zip(axs,['Deadline miss rate (%)','Simulated display PSNR (dB)','Mean completion margin (ms)']):
        ax.set(xlabel='Planned reconstruction budget (ms)',ylabel=y);ax.grid(alpha=.18)
    top=axs[0].secondary_xaxis('top',functions=(lambda x:19-x,lambda x:19-x))
    top.set_xlabel('Synthetic release delay (ms)',fontsize=9)
    axs[0].set_ylim(-3,103);axs[2].axhline(0,color='gray',ls=':',lw=1);axs[0].legend(ncol=2)
    save(fig,'budget_sweep')
    # Observed run-to-run variation is reported without treating repetitions
    # of the same clip as independent scenes.
    pr=pd.DataFrame(per_round)
    variability=pr.groupby(['scenario','policy'])[['miss_rate','displayed_psnr_db','generated_psnr_db']].agg(['mean','std'])
    variability.to_csv(root/'run_variability.csv')
    transitions=[]
    for (scenario,policy,round_),g in d.groupby(['scenario','policy','round']):
        g=g.sort_values('index');made=g[g.generated==1]
        switches=(made.config!=made.config.shift()).sum()-int(len(made)>0)
        transitions.append(dict(scenario=scenario,policy=policy,round=round_,
            configuration_switches=int(switches),maximum_consecutive_misses=longest_miss(g.miss),
            mean_absolute_generated_psnr_step_db=made.generated_stereo_psnr_db.diff().abs().mean(),
            mean_absolute_display_psnr_step_db=g.display_stereo_psnr_db.diff().abs().mean()))
    pd.DataFrame(transitions).to_csv(root/'transition_summary.csv',index=False)
    fig,axs=plt.subplots(1,3,figsize=(12,3.1),constrained_layout=True)
    for ax,scenario in zip(axs,['phase','burst','seeded']):
        for i,p in enumerate(POLICIES):
            z=s[(s.policy==p)&(s.scenario==scenario)].iloc[0]
            ax.scatter(z.miss_rate*100,z.displayed_psnr_db,color=COLORS[i],marker='*' if i>=6 else 'o',s=100 if i>=6 else 35,label=LABELS[i])
        ax.set(title=scenario.capitalize(),xlabel='Deadline miss rate (%)',ylabel='Simulated display PSNR (dB)');ax.grid(alpha=.18)
    axs[0].legend(ncol=2);save(fig,'miss_quality')
    fig,axs=plt.subplots(1,3,figsize=(12,3.1),constrained_layout=True)
    for ax,scenario in zip(axs,['phase','burst','seeded']):
        for i,p in enumerate(POLICIES):
            z=s[(s.policy==p)&(s.scenario==scenario)].iloc[0]
            ax.scatter(z.miss_rate*100,z.displayed_center_psnr_db,color=COLORS[i],marker='*' if i>=6 else 'o',s=100 if i>=6 else 35,label=LABELS[i])
        ax.set(title=scenario.capitalize(),xlabel='Deadline miss rate (%)',ylabel='Simulated display center PSNR (dB)');ax.grid(alpha=.18)
    axs[0].legend(ncol=2);save(fig,'miss_center_quality')
    control='budget_07' if 'budget_07' in set(d.scenario) else 'budget_06'
    fig,axs=plt.subplots(1,2,figsize=(7,3),constrained_layout=True)
    for i,p in enumerate(POLICIES):
        g=d[(d.scenario==control)&(d.policy==p)&(d.generated==1)]
        t=(g.finish_ms-g.start_ms).mean()
        q=[g.generated_stereo_psnr_db.mean(),(10*np.log10(65025/g.generated_center_mse)).mean()]
        for ax,y in zip(axs,q):ax.scatter(t,y,color=COLORS[i],marker='*' if i>=6 else 'o',s=90 if i>=6 else 35,label=LABELS[i])
    for ax,scope in zip(axs,['Whole stereo','Fixed center']):
        ax.set(xlabel='Mean reconstruction execution (ms)',ylabel=scope+' PSNR (dB)');ax.grid(alpha=.18)
    axs[1].legend(ncol=2,fontsize=7);save(fig,'generated_quality_latency')
    for policy in ['Dynamic_whole','Dynamic_center']:
        g=d[(d.scenario=='phase')&(d.policy==policy)&(d['round']==0)].sort_values('index')
        fig,axs=plt.subplots(4,1,figsize=(7,6),sharex=True,constrained_layout=True)
        axs[0].plot(g['index'],g.budget_ms,color='#203F50');axs[0].set_ylabel('Budget (ms)')
        mapping={'Half':0,'FOV_0.1':1,'FOV_0.25':2,'FOV_0.5':3,'FOV_0.7':4,'Full':5,'Skipped':-1}
        axs[1].step(g['index'],g.config.map(mapping),where='mid',color='#548235');axs[1].set_yticks(range(6),['Half','0.1','0.25','0.5','0.7','Full']);axs[1].set_ylabel('Selected ROI')
        axs[2].plot(g['index'],g.margin_ms.where(g.generated==1),color='#8497B0');axs[2].axhline(0,color='#C00000',ls='--',lw=1);axs[2].set_ylabel('Margin (ms)')
        axs[3].plot(g['index'],g.display_stereo_psnr_db,label='Simulated display',color='#203F50')
        axs[3].plot(g['index'],g.generated_stereo_psnr_db,label='Generated',color='#BF9000',alpha=.8)
        axs[3].set(ylabel='Stereo PSNR (dB)',xlabel='Frame index');axs[3].legend()
        for ax in axs:
            ax.grid(alpha=.15)
            for x in [24,48,72]:ax.axvline(x,color='gray',ls=':',lw=.8)
        save(fig,'timeline_'+policy.lower())
    # Tightest and loosest budgets and individual random intensities remain in
    # the same report; no removal of failed conditions or dominated policies.
    (root/'COMPLETE').write_text('All expected runs and causal/history checks passed.\n')
    print(s[s.scenario.isin(['phase','burst','seeded'])][['scenario','policy','miss_rate','displayed_psnr_db','displayed_center_psnr_db']].to_string(index=False))
    return s,d


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args();analyze(a.root)
