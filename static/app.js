(() => {
  'use strict';
  const d = document;
  const root = d.documentElement;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const coarse = matchMedia('(pointer: coarse)').matches;
  const q = (s, ctx=d) => ctx.querySelector(s);
  const qa = (s, ctx=d) => [...ctx.querySelectorAll(s)];

  /* Theme system */
  const allowed = ['noir','velvet','black-cherry','cosmic','emerald','ultraviolet'];
  const themeColors = {noir:'#0c090a',velvet:'#0d090e','black-cherry':'#0c0809',cosmic:'#0a0a0f',emerald:'#090d0b',ultraviolet:'#0c0a0e'};
  let theme = root.dataset.theme || 'noir';
  if (!allowed.includes(theme)) theme = 'noir';
  const setTheme = (next) => {
    if (!allowed.includes(next)) return;
    theme = next; root.dataset.theme = next;
    try { localStorage.setItem('lunelle-dark-theme', next); } catch (_) {}
    const meta = q('meta[name="theme-color"]'); if (meta) meta.content = themeColors[next];
    qa('[data-theme-choice],[data-onboard-theme]').forEach(el => el.classList.toggle('active', (el.dataset.themeChoice || el.dataset.onboardTheme) === next));
  };
  setTheme(theme);

  const themePanel = q('#themePanel'), themeBackdrop = q('#themeBackdrop');
  const openTheme = () => { if (!themePanel) return; themePanel.hidden = false; themeBackdrop.hidden = false; requestAnimationFrame(() => { themePanel.classList.add('open'); themeBackdrop.classList.add('open'); }); };
  const closeTheme = () => { if (!themePanel) return; themePanel.classList.remove('open'); themeBackdrop.classList.remove('open'); setTimeout(() => { themePanel.hidden = true; themeBackdrop.hidden = true; }, 220); };
  q('#themeBtn')?.addEventListener('click', openTheme); q('#themeBtnMobile')?.addEventListener('click', openTheme); q('#themeClose')?.addEventListener('click', closeTheme); themeBackdrop?.addEventListener('click', closeTheme);
  qa('[data-theme-choice]').forEach(el => el.addEventListener('click', () => { setTheme(el.dataset.themeChoice); setTimeout(closeTheme, 100); }));
  qa('[data-onboard-theme]').forEach(el => el.addEventListener('click', () => setTheme(el.dataset.onboardTheme)));

  /* Starfield canvas */
  const starCanvas = q('#starfield');
  if (starCanvas) {
    const ctx = starCanvas.getContext('2d'); let stars = [], w=0, h=0, raf=0;
    const resize = () => {
      const ratio = Math.min(devicePixelRatio || 1, 2); w = innerWidth; h = innerHeight;
      starCanvas.width = w*ratio; starCanvas.height = h*ratio; starCanvas.style.width=w+'px'; starCanvas.style.height=h+'px'; ctx.setTransform(ratio,0,0,ratio,0,0);
      const count = Math.max(42, Math.min(120, Math.round((w*h)/17000)));
      stars = Array.from({length:count}, () => ({x:Math.random()*w,y:Math.random()*h,r:.35+Math.random()*1.15,a:.08+Math.random()*.5,v:.035+Math.random()*.12,p:Math.random()*Math.PI*2}));
    };
    const draw = (t=0) => {
      ctx.clearRect(0,0,w,h);
      for (const s of stars) {
        const a = s.a*(.58+.42*Math.sin(t*.001*s.v*10+s.p));
        ctx.beginPath(); ctx.fillStyle=`rgba(255,255,255,${a})`; ctx.arc(s.x,s.y,s.r,0,Math.PI*2); ctx.fill();
        if (!reduced) { s.y -= s.v; if (s.y < -3) { s.y=h+3; s.x=Math.random()*w; } }
      }
      if (!reduced) raf=requestAnimationFrame(draw);
    };
    resize(); draw(); addEventListener('resize', resize, {passive:true});
  }

  /* Animated luminous orbital canvases */
  qa('[data-orb-canvas]').forEach((canvas, index) => {
    const ctx = canvas.getContext('2d'); let w=0,h=0,particles=[]; const seed=index*1.7;
    const resize = () => {
      const box=canvas.getBoundingClientRect(), ratio=Math.min(devicePixelRatio||1,2); w=Math.max(1,box.width); h=Math.max(1,box.height);
      canvas.width=w*ratio; canvas.height=h*ratio; ctx.setTransform(ratio,0,0,ratio,0,0);
      particles=Array.from({length:18},(_,i)=>({a:(i/18)*Math.PI*2,r:.27+Math.random()*.16,s:.00008+Math.random()*.00014,z:1+Math.random()*2.4}));
    };
    const rgb = () => getComputedStyle(root).getPropertyValue('--accent-rgb').trim() || '255,79,154';
    const draw = (t=0) => {
      ctx.clearRect(0,0,w,h); const cx=w/2,cy=h/2,base=Math.min(w,h)*.27; const c=rgb();
      const g=ctx.createRadialGradient(cx-w*.05,cy-h*.08,0,cx,cy,base*1.25); g.addColorStop(0,'rgba(255,255,255,.15)');g.addColorStop(.13,`rgba(${c},.22)`);g.addColorStop(.44,`rgba(${c},.055)`);g.addColorStop(1,'rgba(0,0,0,0)');ctx.fillStyle=g;ctx.beginPath();ctx.arc(cx,cy,base*1.25,0,Math.PI*2);ctx.fill();
      for(let ring=0;ring<3;ring++){
        ctx.save();ctx.translate(cx,cy);ctx.rotate((t*.00007*(ring%2?1:-1))+seed+ring*.42);ctx.scale(1,.55+ring*.08);ctx.beginPath();ctx.strokeStyle=`rgba(${c},${.15-ring*.03})`;ctx.lineWidth=.7;ctx.arc(0,0,base*(1.18+ring*.28),0,Math.PI*2);ctx.stroke();ctx.restore();
      }
      particles.forEach((p,i)=>{const a=p.a+(reduced?0:t*p.s);const rr=base*(1.2+p.r);const x=cx+Math.cos(a)*rr;const y=cy+Math.sin(a)*rr*.61;ctx.beginPath();ctx.fillStyle=i%4===0?'rgba(255,255,255,.8)':`rgba(${c},.55)`;ctx.shadowBlur=12;ctx.shadowColor=`rgba(${c},.5)`;ctx.arc(x,y,p.z,0,Math.PI*2);ctx.fill();ctx.shadowBlur=0;});
      if(!reduced) requestAnimationFrame(draw);
    };
    resize(); draw(); addEventListener('resize',resize,{passive:true});
  });

  /* Pointer aura */
  const aura=q('#cursorAura'); if(aura && !coarse){addEventListener('pointermove',e=>{aura.style.left=e.clientX+'px';aura.style.top=e.clientY+'px';},{passive:true});}

  /* Scroll progress + compact nav */
  const progress=q('#scrollProgress'), nav=q('#siteNav');
  const onScroll=()=>{const max=d.documentElement.scrollHeight-innerHeight; if(progress) progress.style.width=(max>0?(scrollY/max)*100:0)+'%'; nav?.classList.toggle('scrolled',scrollY>18);};
  addEventListener('scroll',onScroll,{passive:true}); onScroll();

  /* Intersection reveals */
  if(!reduced && 'IntersectionObserver' in window){
    const io=new IntersectionObserver(entries=>entries.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in-view');io.unobserve(e.target);}}),{threshold:.12,rootMargin:'0px 0px -40px'});
    qa('.reveal,.reveal-group').forEach(el=>io.observe(el));
  } else qa('.reveal,.reveal-group').forEach(el=>el.classList.add('in-view'));

  /* Reactive card spotlight */
  if(!coarse) qa('.spotlight-card').forEach(card=>card.addEventListener('pointermove',e=>{const r=card.getBoundingClientRect();card.style.setProperty('--spot-x',`${e.clientX-r.left}px`);card.style.setProperty('--spot-y',`${e.clientY-r.top}px`);}));

  /* Spring-lite parallax on hero stage */
  const stage=q('[data-parallax-stage]');
  if(stage && !coarse && !reduced){
    let tx=0,ty=0,cx=0,cy=0;
    stage.addEventListener('pointermove',e=>{const r=stage.getBoundingClientRect();tx=((e.clientX-r.left)/r.width-.5);ty=((e.clientY-r.top)/r.height-.5);});
    stage.addEventListener('pointerleave',()=>{tx=ty=0;});
    const frame=()=>{cx+=(tx-cx)*.07;cy+=(ty-cy)*.07;qa('[data-parallax]',stage).forEach(el=>{const m=Number(el.dataset.parallax||1);el.style.translate=`${cx*18*m}px ${cy*14*m}px`;el.style.rotate=`${cx*1.5*m}deg`;});requestAnimationFrame(frame)};frame();
  }

  /* Magnetic buttons */
  if(!coarse && !reduced) qa('.magnetic').forEach(btn=>{btn.addEventListener('pointermove',e=>{const r=btn.getBoundingClientRect();const x=e.clientX-r.left-r.width/2,y=e.clientY-r.top-r.height/2;btn.style.transform=`translate(${x*.09}px,${y*.12}px) translateY(-2px)`;});btn.addEventListener('pointerleave',()=>btn.style.transform='');});

  /* Ripple interaction */
  qa('.button,.mood-chip,.theme-option').forEach(btn=>btn.addEventListener('pointerdown',e=>{if(reduced)return;const r=btn.getBoundingClientRect(),rip=d.createElement('span');rip.className='ripple';rip.style.left=(e.clientX-r.left)+'px';rip.style.top=(e.clientY-r.top)+'px';btn.appendChild(rip);setTimeout(()=>rip.remove(),700);}));

  /* Command palette */
  const palette=q('#commandPalette'), commandInput=q('#commandInput'); let commandIndex=0;
  const visibleCommands=()=>qa('.command-results a',palette||d).filter(a=>a.style.display!=='none');
  const setCommandActive=(idx)=>{const arr=visibleCommands();if(!arr.length)return;commandIndex=(idx+arr.length)%arr.length;arr.forEach((a,i)=>a.classList.toggle('active',i===commandIndex));arr[commandIndex].scrollIntoView({block:'nearest'});};
  const openCommand=()=>{if(!palette)return;palette.hidden=false;requestAnimationFrame(()=>palette.classList.add('open'));setTimeout(()=>commandInput?.focus(),80);commandIndex=0;setCommandActive(0);};
  const closeCommand=()=>{if(!palette)return;palette.classList.remove('open');setTimeout(()=>{palette.hidden=true;if(commandInput){commandInput.value='';qa('.command-results a',palette).forEach(a=>a.style.display='');}},200);};
  q('#commandOpen')?.addEventListener('click',openCommand);
  palette?.addEventListener('click',e=>{if(e.target===palette)closeCommand();});
  commandInput?.addEventListener('input',()=>{const s=commandInput.value.trim().toLowerCase();qa('.command-results a',palette).forEach(a=>a.style.display=(!s||a.dataset.command.includes(s)||a.textContent.toLowerCase().includes(s))?'':'none');commandIndex=0;setCommandActive(0);});
  addEventListener('keydown',e=>{
    if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();palette?.hidden?openCommand():closeCommand();return;}
    if(!palette||palette.hidden)return;
    if(e.key==='Escape'){closeCommand();return;} if(e.key==='ArrowDown'){e.preventDefault();setCommandActive(commandIndex+1);} if(e.key==='ArrowUp'){e.preventDefault();setCommandActive(commandIndex-1);} if(e.key==='Enter'){const a=visibleCommands()[commandIndex];if(a){e.preventDefault();location.href=a.href;}}
  });

  /* Quick-add sheet */
  const quick=q('#quickSheet'), fab=q('#quickFab');
  const openQuick=()=>{if(!quick)return;quick.hidden=false;requestAnimationFrame(()=>{quick.classList.add('open');fab?.classList.add('open')});};
  const closeQuick=()=>{if(!quick)return;quick.classList.remove('open');fab?.classList.remove('open');setTimeout(()=>quick.hidden=true,230);};
  fab?.addEventListener('click',()=>quick?.hidden?openQuick():closeQuick()); q('#mobileQuick')?.addEventListener('click',openQuick); q('#quickClose')?.addEventListener('click',closeQuick);

  /* Privacy blur */
  q('#privacyToggle')?.addEventListener('click',function(){const on=d.body.classList.toggle('privacy-on');this.classList.toggle('active',on);this.title=on?'Show private details':'Privacy blur';});

  /* Animated counts / progress */
  qa('[data-count]').forEach(el=>{const n=Number(el.dataset.count);if(!Number.isFinite(n)||reduced)return;const start=performance.now(),dur=720;const tick=now=>{const p=Math.min(1,(now-start)/dur),ease=1-Math.pow(1-p,3);el.textContent=Math.round(n*ease);if(p<1)requestAnimationFrame(tick)};requestAnimationFrame(tick);});
  qa('.goal-track i,.moon-meter i').forEach(el=>{const width=el.style.width;el.style.width='0';requestAnimationFrame(()=>setTimeout(()=>el.style.width=width,120));});

  /* Password toggle + strength */
  qa('[data-password-toggle]').forEach(btn=>btn.addEventListener('click',()=>{const input=q('#'+btn.dataset.passwordToggle);if(!input)return;const show=input.type==='text';input.type=show?'password':'text';btn.textContent=show?'Show':'Hide';}));
  const signupPassword=q('#signupPassword'), meter=q('[data-password-meter]');
  signupPassword?.addEventListener('input',()=>{const v=signupPassword.value;let score=0;if(v.length>=8)score++;if(v.length>=12)score++;if(/[A-Z]/.test(v)&&/[a-z]/.test(v))score++;if(/\d/.test(v))score++;if(/[^A-Za-z0-9]/.test(v))score++;const pct=Math.max(12,score*20);meter?.style.setProperty('--strength',pct+'%');const label=meter?.querySelector('small');if(label)label.textContent=score<=1?'Keep going':score<=3?'Good password':'Strong password';});

  /* Onboarding wizard */
  const onboarding=q('[data-onboarding]');
  if(onboarding){let step=1;const steps=qa('[data-step]',onboarding),bars=qa('.onboarding-progress i',onboarding),label=q('#onboardingStepLabel');const show=s=>{step=Math.max(1,Math.min(3,s));steps.forEach(el=>el.classList.toggle('active',Number(el.dataset.step)===step));bars.forEach((el,i)=>el.classList.toggle('active',i<step));if(label)label.textContent=step;};qa('[data-next]',onboarding).forEach(b=>b.addEventListener('click',()=>show(step+1)));qa('[data-prev]',onboarding).forEach(b=>b.addEventListener('click',()=>show(step-1)));show(1);}

  /* Flash toasts */
  qa('[data-flash]').forEach((toast,i)=>{toast.querySelector('button')?.addEventListener('click',()=>toast.classList.add('out'));setTimeout(()=>toast.classList.add('out'),5000+i*300);});

  /* Smooth exit for internal GET navigation */
  qa('a[data-nav-link]').forEach(a=>a.addEventListener('click',e=>{if(reduced||e.metaKey||e.ctrlKey||e.shiftKey||a.target==='_blank'||a.href.includes('#'))return;const u=new URL(a.href,location.href);if(u.origin!==location.origin)return;e.preventDefault();d.body.classList.add('page-leaving');setTimeout(()=>location.href=a.href,150);}));

  /* PWA */
  if('serviceWorker' in navigator) addEventListener('load',()=>navigator.serviceWorker.register('/sw.js').catch(()=>{}));
  let installPrompt=null;const installButtons=[q('#installApp'),q('#installApp2')].filter(Boolean);const syncInstall=()=>installButtons.forEach(b=>{b.hidden=!installPrompt;b.disabled=!installPrompt;});addEventListener('beforeinstallprompt',e=>{e.preventDefault();installPrompt=e;syncInstall();});installButtons.forEach(b=>b.addEventListener('click',async()=>{if(!installPrompt)return;installPrompt.prompt();await installPrompt.userChoice;installPrompt=null;syncInstall();}));syncInstall();

  /* Sky Link — location-aware sunrise, sunset, moon and stars */
  const skyPage=q('[data-sky-page]');
  const skyLocate=q('#skyLocate'), skyLinkToggle=q('#skyLinkToggle'), skyRemember=q('#skyRemember');
  const skyEls={
    state:q('#skyStateLabel'),clock:q('#skyClock'),caption:q('#skyDomeCaption'),pill:q('#skyStatePill'),
    sunrise:q('#sunriseTime'),sunset:q('#sunsetTime'),dusk:q('#duskTime'),dawn:q('#dawnTime'),
    moonrise:q('#moonriseTime'),moonset:q('#moonsetTime'),moonName:q('#liveMoonName'),moonDetail:q('#liveMoonDetail'),moonSign:q('#liveMoonSign'),moonVisual:q('#liveMoonVisual'),
    score:q('#skyScore strong'),quality:q('#skyQuality'),darkStart:q('#darkStart'),darkEnd:q('#darkEnd'),stars:q('#visibleStars'),planets:q('#planetWatch'),planetTime:q('#planetViewTime'),sunDot:q('#sunDot')
  };
  let skyData=null, skyStars=[], skyRaf=0;
  const skyStateNames={dawn:'Astronomical dawn',sunrise:'Sunrise glow',day:'Daylight',golden:'Golden hour',twilight:'Blue hour',stars:'Starlight'};
  const setSkyState=(state)=>{
    const linked=localStorage.getItem('lunelle-sky-linked')==='1';
    if(linked && state){d.body.dataset.skyState=state;d.body.classList.add('sky-linked');localStorage.setItem('lunelle-sky-state',state);} else if(!linked){d.body.classList.remove('sky-linked');}
    if(skyLinkToggle){skyLinkToggle.textContent=linked?'Sky appearance linked ✓':'Link appearance to sky';skyLinkToggle.classList.toggle('active',linked);}
  };
  const savedSkyState=localStorage.getItem('lunelle-sky-state'); if(localStorage.getItem('lunelle-sky-linked')==='1'&&savedSkyState){d.body.dataset.skyState=savedSkyState;d.body.classList.add('sky-linked');}
  if(skyRemember) skyRemember.checked=!!localStorage.getItem('lunelle-sky-location');
  skyLinkToggle?.addEventListener('click',()=>{const next=localStorage.getItem('lunelle-sky-linked')!=='1';localStorage.setItem('lunelle-sky-linked',next?'1':'0');setSkyState(skyData?.state||savedSkyState||'stars');});
  setSkyState(skyData?.state||savedSkyState||'stars');

  const fmtSky=(obj)=>obj?.time||'—';
  const isoTime=(iso)=>{if(!iso)return null;const t=new Date(iso);return Number.isFinite(t.getTime())?t:null;};
  const setSolarDot=(data)=>{
    if(!skyEls.sunDot)return;const now=isoTime(data.local_now),sr=isoTime(data.sunrise?.iso),ss=isoTime(data.sunset?.iso);let x=6,y=83;
    if(now&&sr&&ss&&now>=sr&&now<=ss){const p=Math.max(0,Math.min(1,(now-sr)/(ss-sr)));x=8+p*84;y=78-Math.sin(Math.PI*p)*62;}else if(now&&sr&&now<sr){x=5;y=83;}else{x=95;y=83;}
    skyEls.sunDot.style.setProperty('--sun-x',x+'%');skyEls.sunDot.style.setProperty('--sun-y',y+'%');
  };
  const updateMoonVisual=(moon)=>{if(!skyEls.moonVisual)return;const shade=skyEls.moonVisual.querySelector('i');if(!shade)return;const illum=Math.max(0,Math.min(100,moon.illumination||0));const dir=(moon.angle||0)<=180?1:-1;shade.style.transform=`translateX(${dir*illum*1.08}%)`;};
  const renderSky=(data)=>{
    skyData=data;skyStars=data.stars||[];setSkyState(data.state);d.body.classList.remove('sky-loading');q('#skyLive')?.classList.remove('is-waiting');
    const now=isoTime(data.local_now); if(skyEls.clock&&now)skyEls.clock.textContent=now.toLocaleTimeString([], {hour:'numeric',minute:'2-digit'});
    if(skyEls.state)skyEls.state.textContent=skyStateNames[data.state]||data.state;if(skyEls.pill)skyEls.pill.textContent=skyStateNames[data.state]||data.state;
    if(skyEls.caption)skyEls.caption.textContent=`Bright-star map for ${data.view_time} • ${data.timezone}`;
    if(skyEls.sunrise)skyEls.sunrise.textContent=fmtSky(data.sunrise);if(skyEls.sunset)skyEls.sunset.textContent=fmtSky(data.sunset);if(skyEls.dusk)skyEls.dusk.textContent=fmtSky(data.astronomical_dusk);if(skyEls.dawn)skyEls.dawn.textContent=fmtSky(data.astronomical_dawn);
    if(skyEls.moonrise)skyEls.moonrise.textContent=fmtSky(data.moonrise);if(skyEls.moonset)skyEls.moonset.textContent=fmtSky(data.moonset);
    if(skyEls.moonName)skyEls.moonName.textContent=data.moon.name;if(skyEls.moonDetail)skyEls.moonDetail.textContent=`${data.moon.illumination}% illuminated`;if(skyEls.moonSign)skyEls.moonSign.textContent=`Moon in ${data.moon.sign}`;updateMoonVisual(data.moon);setSolarDot(data);
    if(skyEls.score)skyEls.score.textContent=data.stargazing_score;if(skyEls.quality)skyEls.quality.textContent=`${data.stargazing_quality}. This score considers astronomical darkness and moonlight, not clouds or local light pollution.`;
    if(skyEls.darkStart)skyEls.darkStart.textContent=data.dark_start?`Dark from ${data.dark_start.time}`:'Darkness begins later';if(skyEls.darkEnd)skyEls.darkEnd.textContent=data.dark_end?`until ${data.dark_end.time}`:'';
    if(skyEls.stars){skyEls.stars.innerHTML=skyStars.length?skyStars.map(st=>`<article class="star-chip"><strong>${st.name}</strong><span>${st.constellation}</span><small>${st.altitude}° high • az ${Math.round(st.azimuth)}°</small></article>`).join(''):'<div class="empty">No catalogued bright stars are above the 5° horizon at the selected view time.</div>';}
    if(skyEls.planetTime)skyEls.planetTime.textContent=`View at ${data.view_time}`;if(skyEls.planets){const planets=data.planets||[];skyEls.planets.innerHTML=planets.length?planets.map(p=>`<article class="planet-watch-card"><span>${p.symbol}</span><div><strong>${p.name}</strong><small>${p.altitude}° high • az ${Math.round(p.azimuth)}° • mag ${p.magnitude}</small></div></article>`).join(''):'<div class="empty">None of the five bright naked-eye planets are above 5° at this viewing time.</div>';}
    drawSkyDome();
    try{localStorage.setItem('lunelle-sky-cache',JSON.stringify({at:Date.now(),data:{state:data.state,sunrise:data.sunrise,sunset:data.sunset,astronomical_dusk:data.astronomical_dusk,astronomical_dawn:data.astronomical_dawn,moon:data.moon}}));}catch(_){ }
  };
  const skyError=(msg)=>{d.body.classList.remove('sky-loading');if(skyPage){let el=q('.sky-error',skyPage);if(!el){el=d.createElement('div');el.className='sky-error';skyPage.querySelector('.sky-copy')?.appendChild(el);}el.textContent=msg;}};
  const fetchSky=async(lat,lon)=>{const tz=Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC';d.body.classList.add('sky-loading');try{const r=await fetch(`/api/sky?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&tz=${encodeURIComponent(tz)}`,{headers:{'Accept':'application/json'}});const data=await r.json();if(!r.ok||data.error)throw new Error(data.error||'Sky data unavailable');renderSky(data);return data;}catch(err){skyError(err.message||'Could not calculate your sky.');return null;}};
  const locateSky=()=>{if(!navigator.geolocation){skyError('Location is not available in this browser. You can still use the lunar clock above.');return;}skyLocate&&(skyLocate.disabled=true,skyLocate.textContent='Locating sky…');navigator.geolocation.getCurrentPosition(async pos=>{const lat=pos.coords.latitude,lon=pos.coords.longitude;if(skyRemember?.checked){try{localStorage.setItem('lunelle-sky-location',JSON.stringify({lat:Number(lat.toFixed(2)),lon:Number(lon.toFixed(2))}));}catch(_){}}else{try{localStorage.removeItem('lunelle-sky-location');}catch(_){}}await fetchSky(lat,lon);if(skyLocate){skyLocate.disabled=false;skyLocate.innerHTML='<span class="button-spark">✦</span> Refresh my sky';}},err=>{skyError(err.code===1?'Location permission was declined. Lunelle will not request it again unless you tap the button.':'Could not read your location.');if(skyLocate){skyLocate.disabled=false;skyLocate.innerHTML='<span class="button-spark">✦</span> Try location again';}},{enableHighAccuracy:false,timeout:9000,maximumAge:600000});};
  skyLocate?.addEventListener('click',locateSky);
  skyRemember?.addEventListener('change',()=>{if(!skyRemember.checked)localStorage.removeItem('lunelle-sky-location');});

  const dome=q('#skyDome');
  const drawSkyDome=()=>{if(!dome)return;cancelAnimationFrame(skyRaf);const ctx=dome.getContext('2d');let start=performance.now();const draw=(t)=>{const rect=dome.getBoundingClientRect(),ratio=Math.min(devicePixelRatio||1,2);if(dome.width!==Math.round(rect.width*ratio)||dome.height!==Math.round(rect.height*ratio)){dome.width=Math.round(rect.width*ratio);dome.height=Math.round(rect.height*ratio);ctx.setTransform(ratio,0,0,ratio,0,0);}const w=rect.width,h=rect.height,cx=w/2,cy=h/2,r=Math.min(w,h)*.43;ctx.clearRect(0,0,w,h);
      for(let ring=1;ring<=3;ring++){ctx.beginPath();ctx.strokeStyle='rgba(255,255,255,.045)';ctx.lineWidth=1;ctx.arc(cx,cy,r*ring/3,0,Math.PI*2);ctx.stroke();}
      skyStars.forEach((st,i)=>{const rr=r*(1-Math.max(0,Math.min(90,st.altitude))/90);const a=(st.azimuth-90)*Math.PI/180;const x=cx+Math.cos(a)*rr,y=cy+Math.sin(a)*rr;const pulse=reduced?1:.78+.22*Math.sin(t*.002+i*1.7);const size=Math.max(1.4,4.2-(st.magnitude+1)*.75)*pulse;ctx.beginPath();ctx.fillStyle=`rgba(255,255,255,${.62+.28*pulse})`;ctx.shadowBlur=10;ctx.shadowColor='rgba(186,184,255,.55)';ctx.arc(x,y,size,0,Math.PI*2);ctx.fill();ctx.shadowBlur=0;if(i<8&&rect.width>430){ctx.font='9px system-ui';ctx.fillStyle='rgba(255,255,255,.55)';ctx.fillText(st.name,x+7,y-6);}});
      if(!reduced){const cycle=((t-start)%9000)/9000;if(cycle>.72&&cycle<.82){const p=(cycle-.72)/.10;ctx.beginPath();ctx.moveTo(w*.16+p*w*.42,h*.18+p*h*.2);ctx.lineTo(w*.08+p*w*.42,h*.12+p*h*.2);const g=ctx.createLinearGradient(w*.08,h*.12,w*.6,h*.4);g.addColorStop(0,'transparent');g.addColorStop(1,'rgba(255,255,255,.8)');ctx.strokeStyle=g;ctx.lineWidth=1.2;ctx.stroke();}skyRaf=requestAnimationFrame(draw);}};skyRaf=requestAnimationFrame(draw);};
  if(dome)drawSkyDome();

  // If the user explicitly chose "Keep Sky Sync", refresh rounded coordinates automatically.
  try{const remembered=JSON.parse(localStorage.getItem('lunelle-sky-location')||'null');if(d.body.classList.contains('is-authenticated')&&remembered&&Number.isFinite(remembered.lat)&&Number.isFinite(remembered.lon)){if(skyRemember)skyRemember.checked=true;fetchSky(remembered.lat,remembered.lon);}else{const cached=JSON.parse(localStorage.getItem('lunelle-sky-cache')||'null');if(cached&&Date.now()-cached.at<30*60*1000&&localStorage.getItem('lunelle-sky-linked')==='1')setSkyState(cached.data.state);}}catch(_){ }

  /* Live lunar countdown labels */
  const updateLunarCountdowns=()=>qa('[data-lunar-event]').forEach(card=>{const target=new Date(card.dataset.lunarEvent),out=q('[data-lunar-countdown]',card);if(!out||!Number.isFinite(target.getTime()))return;const ms=Math.max(0,target-Date.now()),days=Math.floor(ms/86400000),hours=Math.floor((ms%86400000)/3600000),mins=Math.floor((ms%3600000)/60000);out.textContent=days?`${days}d ${hours}h away`:`${hours}h ${mins}m away`;});
  updateLunarCountdowns(); if(qa('[data-lunar-event]').length)setInterval(updateLunarCountdowns,60000);

  /* Optional notifications */
  const notify=q('#notifyPermission'),notifyStatus=q('#notifyStatus');if(notify){const show=m=>{if(notifyStatus)notifyStatus.textContent=m};if(!('Notification'in window)){notify.disabled=true;show('Notifications are not supported here.');}else{show(`Current permission: ${Notification.permission}`);notify.addEventListener('click',async()=>{const p=await Notification.requestPermission();show(`Current permission: ${p}`);if(p==='granted')new Notification('Lunelle',{body:'Gentle reminders are enabled while Lunelle is available.'});});}}


  /* Lunelle Universe — interactive time scrubber */
  const universe = q('#lunelleUniverse');
  const universeCanvas = q('#universeCanvas');
  const scrubber = q('#universeScrubber');
  if (universe && universeCanvas && scrubber) {
    let universeData=[];
    try { universeData=JSON.parse(universe.dataset.universe||'[]'); } catch(_) {}
    const ctx=universeCanvas.getContext('2d');
    const center=q('.universe-center',universe), dayOut=q('#universeCycleDay'), phaseOut=q('#universePhase'), dateOut=q('#universeDate'), labelOut=q('#universeSelectedLabel'), moonOut=q('#universeMoon');
    const todayBtn=q('#universeToday');
    const phaseHue=(name)=> name?.includes('Menstrual') ? 338 : name?.includes('fertile') ? 283 : name?.includes('Follicular') ? 205 : name?.includes('Luteal') ? 258 : 230;
    let selected=0, raf=0, start=performance.now();
    const getSelected=()=>universeData.find(x=>Number(x.offset)===selected)||universeData.find(x=>Number(x.offset)===0)||universeData[0];
    const updateUniverse=()=>{
      selected=Number(scrubber.value||0); const item=getSelected(); if(!item)return;
      if(dayOut) dayOut.textContent=item.cycle_day||'—'; if(phaseOut) phaseOut.textContent=item.phase; if(dateOut) dateOut.textContent=item.offset===0?'Today':item.label;
      if(labelOut) labelOut.textContent=item.offset===0?'Today':item.label;
      if(moonOut) moonOut.innerHTML=`<b>${item.moon_icon}</b><span>${item.moon} · ${item.illumination}%</span>`;
      const hue=phaseHue(item.phase); universe.style.setProperty('--universe-hue',hue); universe.style.setProperty('--universe-progress',Math.max(0,Math.min(1,(Number(item.cycle_day||1)-1)/Math.max(21,Number(item.cycle_day||1)))));
      center?.animate([{transform:'scale(.94)',filter:'blur(2px)'},{transform:'scale(1)',filter:'blur(0)'}],{duration:420,easing:'cubic-bezier(.2,.8,.2,1)'});
    };
    const drawUniverse=(t)=>{
      const rect=universeCanvas.getBoundingClientRect(),ratio=Math.min(devicePixelRatio||1,2);
      if(universeCanvas.width!==Math.round(rect.width*ratio)||universeCanvas.height!==Math.round(rect.height*ratio)){universeCanvas.width=Math.round(rect.width*ratio);universeCanvas.height=Math.round(rect.height*ratio);ctx.setTransform(ratio,0,0,ratio,0,0);}
      const w=rect.width,h=rect.height,cx=w/2,cy=h/2,r=Math.min(w,h)*.42,item=getSelected();ctx.clearRect(0,0,w,h);
      const hue=phaseHue(item?.phase||'');
      // faint star dust
      for(let i=0;i<58;i++){const a=i*12.9898,rr=((i*37)%100)/100*r*.98,x=cx+Math.cos(a)*rr,y=cy+Math.sin(a*1.31)*rr;const pulse=reduced?1:.55+.45*Math.sin(t*.0013+i);ctx.beginPath();ctx.fillStyle=`hsla(${220+i%35},80%,88%,${.05+.12*pulse})`;ctx.arc(x,y,(i%5===0?1.5:.7)*pulse,0,Math.PI*2);ctx.fill();}
      // orbit rings
      [1,.72,.49].forEach((mul,n)=>{ctx.beginPath();ctx.strokeStyle=`rgba(255,255,255,${.065-n*.012})`;ctx.lineWidth=1;ctx.setLineDash(n===1?[4,8]:[]);ctx.arc(cx,cy,r*mul,0,Math.PI*2);ctx.stroke();ctx.setLineDash([]);});
      // cycle arc
      const cycleDay=Math.max(1,Number(item?.cycle_day||1)),cycleLen=28,progress=((cycleDay-1)%cycleLen)/cycleLen;ctx.beginPath();ctx.lineWidth=4;ctx.lineCap='round';ctx.strokeStyle=`hsla(${hue},92%,68%,.9)`;ctx.shadowBlur=20;ctx.shadowColor=`hsla(${hue},92%,60%,.45)`;ctx.arc(cx,cy,r*.72,-Math.PI/2,-Math.PI/2+progress*Math.PI*2);ctx.stroke();ctx.shadowBlur=0;
      // rotating cycle bead
      const cycleA=-Math.PI/2+progress*Math.PI*2,x1=cx+Math.cos(cycleA)*r*.72,y1=cy+Math.sin(cycleA)*r*.72;ctx.beginPath();ctx.fillStyle=`hsl(${hue},96%,72%)`;ctx.shadowBlur=26;ctx.shadowColor=`hsl(${hue},96%,60%)`;ctx.arc(x1,y1,7,0,Math.PI*2);ctx.fill();ctx.shadowBlur=0;
      // moon bead rotates slowly with real phase angle-ish position
      const moonP=((Number(item?.illumination||0)/100)+(item?.moon?.includes('Waning')?.5:0))%1; const drift=reduced?0:(t-start)*.000025; const ma=-Math.PI/2+(moonP+drift)%1*Math.PI*2; const mx=cx+Math.cos(ma)*r,my=cy+Math.sin(ma)*r;ctx.beginPath();ctx.fillStyle='rgba(232,230,255,.95)';ctx.shadowBlur=22;ctx.shadowColor='rgba(150,130,255,.65)';ctx.arc(mx,my,5.5,0,Math.PI*2);ctx.fill();ctx.shadowBlur=0;
      // gentle spokes
      for(let i=0;i<12;i++){const a=i*Math.PI/6+drift*.2;ctx.beginPath();ctx.strokeStyle='rgba(255,255,255,.025)';ctx.moveTo(cx+Math.cos(a)*r*.49,cy+Math.sin(a)*r*.49);ctx.lineTo(cx+Math.cos(a)*r,cy+Math.sin(a)*r);ctx.stroke();}
      if(!reduced)raf=requestAnimationFrame(drawUniverse);
    };
    scrubber.addEventListener('input',updateUniverse); todayBtn?.addEventListener('click',()=>{scrubber.value='0';updateUniverse();}); updateUniverse(); drawUniverse(performance.now());
  }

  /* Wrapped story player */
  const wrapped=q('#wrappedStory');
  if(wrapped){
    const slides=qa('[data-wrapped-slide]',wrapped),bars=qa('.wrapped-progress i',wrapped),count=q('#wrappedCount',wrapped);let wi=0,touchX=null;
    const showWrapped=(next)=>{if(!slides.length)return;wi=(next+slides.length)%slides.length;slides.forEach((el,i)=>el.classList.toggle('active',i===wi));bars.forEach((el,i)=>el.classList.toggle('active',i<=wi));if(count)count.textContent=`${wi+1} / ${slides.length}`;const slide=slides[wi];slide?.animate([{opacity:.3,transform:'translateX(22px) scale(.985)'},{opacity:1,transform:'none'}],{duration:480,easing:'cubic-bezier(.2,.8,.2,1)'});};
    q('#wrappedNext',wrapped)?.addEventListener('click',()=>showWrapped(wi+1));q('#wrappedPrev',wrapped)?.addEventListener('click',()=>showWrapped(wi-1));
    wrapped.addEventListener('touchstart',e=>{touchX=e.touches[0]?.clientX??null},{passive:true});wrapped.addEventListener('touchend',e=>{if(touchX==null)return;const dx=(e.changedTouches[0]?.clientX??touchX)-touchX;if(Math.abs(dx)>45)showWrapped(wi+(dx<0?1:-1));touchX=null},{passive:true});
    d.addEventListener('keydown',e=>{if(!wrapped)return;if(e.key==='ArrowRight')showWrapped(wi+1);if(e.key==='ArrowLeft')showWrapped(wi-1);});
  }


  /* Memory Constellation — each journal entry becomes a deterministic star */
  const memoryCanvas=q('#memoryConstellation');
  if(memoryCanvas){
    const stars=qa('[data-memory-star]').map((el,i)=>({i,seed:(el.textContent||'').length*17+i*97}));
    const mctx=memoryCanvas.getContext('2d'); let mraf=0;
    const drawMemory=(t)=>{const rect=memoryCanvas.getBoundingClientRect(),ratio=Math.min(devicePixelRatio||1,2);if(memoryCanvas.width!==Math.round(rect.width*ratio)||memoryCanvas.height!==Math.round(rect.height*ratio)){memoryCanvas.width=Math.round(rect.width*ratio);memoryCanvas.height=Math.round(rect.height*ratio);mctx.setTransform(ratio,0,0,ratio,0,0);}const w=rect.width,h=rect.height;mctx.clearRect(0,0,w,h);const pts=stars.map((s,i)=>{const x=w*(.43+(((s.seed*13)%503)/503)*.52),y=h*(.1+(((s.seed*29)%467)/467)*.78);return{x,y,i};});
      pts.forEach((a,i)=>{if(i<pts.length-1){const b=pts[i+1];mctx.beginPath();mctx.strokeStyle='rgba(205,184,255,.09)';mctx.moveTo(a.x,a.y);mctx.lineTo(b.x,b.y);mctx.stroke();}if(i>2&&i%3===0){const b=pts[i-3];mctx.beginPath();mctx.strokeStyle='rgba(255,123,183,.045)';mctx.moveTo(a.x,a.y);mctx.lineTo(b.x,b.y);mctx.stroke();}});
      pts.forEach((p,i)=>{const pulse=reduced?1:.75+.25*Math.sin(t*.0015+i*1.9);mctx.beginPath();mctx.fillStyle=`rgba(255,255,255,${.55+.35*pulse})`;mctx.shadowBlur=15;mctx.shadowColor=i%2?'rgba(201,160,255,.7)':'rgba(255,120,180,.62)';mctx.arc(p.x,p.y,(2.2+(i%4)*.7)*pulse,0,Math.PI*2);mctx.fill();mctx.shadowBlur=0;});
      if(!reduced)mraf=requestAnimationFrame(drawMemory);};drawMemory(performance.now());
  }
})();

/* Lunelle v1.5 visual interactions */
(() => {
  const d=document;
  const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Highlight the current app destination.
  const here=location.pathname.replace(/\/$/,'')||'/';
  d.querySelectorAll('.primary-links a,.secondary-links a,.simple-mobile-dock a').forEach(a=>{
    try{const p=new URL(a.href,location.origin).pathname.replace(/\/$/,'')||'/'; if(p===here)a.classList.add('is-current');}catch(_){}
  });

  // Localized soft light follows the pointer inside cards.
  d.querySelectorAll('.spotlight-card').forEach(card=>{
    card.addEventListener('pointermove',e=>{const r=card.getBoundingClientRect();card.style.setProperty('--spot-x',`${e.clientX-r.left}px`);card.style.setProperty('--spot-y',`${e.clientY-r.top}px`);});
  });

  if(!reduced){
    // Magnetic movement on primary controls.
    d.querySelectorAll('.magnetic').forEach(el=>{
      el.addEventListener('pointermove',e=>{const r=el.getBoundingClientRect(),x=e.clientX-(r.left+r.width/2),y=e.clientY-(r.top+r.height/2);el.style.transform=`translate(${x*.08}px,${y*.10}px)`;});
      el.addEventListener('pointerleave',()=>{el.style.transform='';});
    });

    // Tiny spark burst on meaningful taps/clicks.
    d.addEventListener('click',e=>{
      const target=e.target.closest('.vibe-primary,.vibe-checkin,.vibe-moods button,.primary-links a');
      if(!target)return;
      for(let i=0;i<5;i++){
        const s=d.createElement('i');s.className='ui-spark';s.style.left=`${e.clientX}px`;s.style.top=`${e.clientY}px`;
        const a=Math.PI*2*i/5+Math.random()*.5,dist=20+Math.random()*30;s.style.setProperty('--sx',`${Math.cos(a)*dist}px`);s.style.setProperty('--sy',`${Math.sin(a)*dist}px`);
        d.body.appendChild(s);setTimeout(()=>s.remove(),700);
      }
    });
  }
})();
