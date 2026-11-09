import random,math,statistics as st
random.seed(92); D=3041; M=390
days=[]
for _ in range(D):
    p=hi=lo=0.0
    for _ in range(M):
        p+=random.gauss(0,1); hi=max(hi,p); lo=min(lo,p)
    days.append((hi,lo,hi-lo))
def run(n,hw,lb=14,rand=False):
    a=b=c=N=0
    rng=random.Random(7)
    for i in range(lb,D):
        atr=st.fmean(d[2] for d in days[i-lb:i]); hi,lo,_=days[i]
        off=rng.uniform(0,1) if rand else 0
        sp=2.0/ (n/2)
        ctr=[s*(k+.5+off*0)*sp for k in range(n//2) for s in (1,-1)]
        h=any(abs(hi/atr-z)<=hw for z in ctr); l=any(abs(lo/atr-z)<=hw for z in ctr)
        a+=h or l; b+=h and l; c+=h; N+=1
    return round(100*a/N,1),round(100*b/N,1),round(100*c/N,1)
print('zones half_width | HOD or LOD | both | HOD')
for n in (4,6,8,10,12):
    for hw in (.05,.10,.15,.20,.30):
        print(n,hw,run(n,hw))
hd=[d[0]/st.fmean(x[2] for x in days[i-14:i]) for i,d in enumerate(days) if i>=14]
print('median HOD distance in ATR',round(st.median(hd),3))
