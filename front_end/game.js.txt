/* Little River — local-first city game with the uploaded Cozy_Game_Assets.
   Hardware integration: window.ecoCitySort('recycling'|'compost'|'paper'|'garbage').
   All image paths below refer to individual PNGs; no concept-sheet crops are drawn.
*/
(() => {
  'use strict';
  const TYPES = ['recycling', 'compost', 'paper', 'garbage'];
  const ICON = {recycling:'icon_recycling', compost:'icon_compost', paper:'icon_paper', garbage:'icon_garbage'};
  const COLORS = {recycling:'#cb8062', compost:'#839b6c', paper:'#b89d79', garbage:'#e4ad55'};
  const CATALOG = [
    {id:'house', name:'Cozy Cottage', desc:'A little home to welcome new neighbours.', base:[9, 4, 1, 12], art:'residential/house_cottage'},
    {id:'library', name:'Community Library', desc:'A place for learning, meeting, and growing together.', base:[10, 3, 3, 11], art:'community/library'},
    {id:'cafe', name:'Corner Café', desc:'A warm cup of something and a friendly place to meet.', base:[9, 6, 1, 14], art:'community/cafe'},
    {id:'park', name:'Riverside Park', desc:'A leafy retreat beside the gentle river.', base:[6, 12, 1, 10], art:'parks/park'},
    {id:'school', name:'Village School', desc:'A bright place for curious minds.', base:[12, 4, 3, 14], art:'community/community_hall'},
    {id:'townhall', name:'Town Hall', desc:'The heart of the village and its celebrations.', base:[13, 5, 3, 15], art:'community/community_hall'},
    {id:'garden', name:'Community Garden', desc:'Fresh vegetables, flowers, and a shared harvest.', base:[6, 13, 0, 8], art:'parks/garden'},
    {id:'market', name:'Farmers’ Market', desc:'Local produce and friendly market stalls.', base:[8, 9, 1, 13], art:'community/market'},
    {id:'bakery', name:'Village Bakery', desc:'A cosy bakery with freshly made treats.', base:[8, 6, 1, 13], art:'commercial/bakery'},
    {id:'community', name:'Community Centre', desc:'A welcoming space for everyone to gather.', base:[11, 5, 2, 13], art:'community/community_hall'},
    {id:'clinic', name:'Health Clinic', desc:'A caring place for our neighbours.', base:[12, 4, 2, 14], art:'commercial/clinic'},
    {id:'studio', name:'Art Studio', desc:'A colourful space for creativity.', base:[9, 4, 3, 11], art:'community/workshop'},
    {id:'bridge', name:'Riverside Bridge', desc:'A new connection across the water.', base:[13, 3, 0, 14], art:'bridges_docks/bridge_stone'},
    {id:'playground', name:'Playground', desc:'A place to play, explore, and make friends.', base:[8, 9, 0, 12], art:'parks/park'}
  ];
  const $ = id => document.getElementById(id);
  const canvas = $('village');
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  const assetPaths = new Set([
    'background/background_sky','background/full_landscape',
    'background/sunny','background/sunset','background/autumn',
    'background/evening','background/misty',
    ...[1,2,3,4,5].map(n => `terrain/grass_0${n}`),
    ...[1,2,3,4,5].map(n => `terrain/path_0${n}`),
    ...[1,2,3,4,5,6,7,8].map(n => `water/water_0${n}`),
    'bridges_docks/bridge_stone','bridges_docks/bridge_wood','props/lamp_post',
    'props/planter','props/arch_flower','props/bench','props/fence_wood',
    'plants/bush_white','plants/bush_yellow','plants/flower_patch_01',
    'plants/flower_patch_02','plants/flower_patch_03','plants/rock_flower',
    'trees/tree_green','trees/tree_cherry','trees/tree_autumn','trees/tree_pine',
    'trees/tree_willow','trees/tree_flower','trees/tree_red',
    ...CATALOG.map(item => item.art),
    ...[0,1,2,3,4,5].map(n => `stages/stage${n}`)
  ]);
  const assetURL=path=>path; // Embedded HTML replaces this with its packaged data URLs.
  const assets = {};
  let state = null;
  assetPaths.forEach(path => {
    const im = new Image();
    assets[path] = im;
    im.onload = () => { if (state) draw(); };
    im.src = assetURL('assets/' + path + '.png');
  });
  function rng(seed) {
    return () => {seed |= 0;seed = seed+0x6D2B79F5|0;
      let x=Math.imul(seed^seed>>>15,1|seed);x=x+Math.imul(x^x>>>7,61|x)^x;
      return ((x^x>>>14)>>>0)/4294967296;};
  }
  function today() {
    const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  }
  function shuffle(list,random) {
    for(let i=list.length-1;i>0;i--){const j=Math.floor(random()*(i+1));[list[i],list[j]]=[list[j],list[i]];}
    return list;
  }
  const STORAGE='little-river-cozy-uploaded-assets-v1';
  const BALANCE_VERSION=2;

  // Use ?background=sunny|sunset|autumn|evening|misty to preview alternate scenes.
  const BACKGROUND_OPTION = new URLSearchParams(location.search).get('background') || 'full_landscape';
  let particles=[],lastEvent=null,toastTimer;
  function requirements(base, random) {
    return base.map((n,i)=>{
      // Paper may legitimately be zero. Avoid turning a low-frequency stream
      // into an impossible gate on a public installation.
      const swing = i===2 ? (n===0?0:1) : (n<=4?1:2);
      return Math.max(i===2?0:1,n+Math.floor(random()*(swing*2+1))-swing);
    });
  }
  function newProjects(day,seed) {
    const random=rng(day*7919+seed);
    return shuffle([...CATALOG],random).slice(0,8).map((p,i)=>({
      key:`${day}-${i}`,id:p.id,need:requirements(p.base,random),
      have:[0,0,0,0],done:false,plot:i
    }));
  }
  function freshState() {
    const seed=Math.floor(Math.random()*1e8);
    return {date:today(),day:1,seed,projects:newProjects(1,seed),active:null,completed:[],total:0,scenery:0,balanceVersion:BALANCE_VERSION};
  }
  function load() {
    try {const value=JSON.parse(localStorage.getItem(STORAGE));if(value&&value.seed!=null&&value.projects?.length){
      if((value.balanceVersion||1)<BALANCE_VERSION){
        // Keep past completed buildings and all already deposited materials.
        // Rebalance today's unfinished projects in place without resetting the city.
        const random=rng(value.seed+value.day*8123+2048);
        for(const p of value.projects){
          if(p.done)continue;
          const item=CATALOG.find(x=>x.id===p.id);if(!item)continue;
          const revised=requirements(item.base,random);
          p.have=p.have.map((n,i)=>{
            value.scenery=(value.scenery||0)+Math.max(0,n-revised[i]);
            return Math.min(n,revised[i]);
          });
          p.need=revised;
          if(p.have.every((n,i)=>n>=p.need[i])){
            p.done=true;
            if(!value.completed.some(c=>c.day===value.day&&c.plot===p.plot))
              value.completed.push({id:p.id,plot:p.plot,day:value.day});
            if(value.active===p.key)value.active=null;
          }
        }
        value.balanceVersion=BALANCE_VERSION;
      }
      return value;
    }}catch(e){}
    return freshState();
  }
  function save() {try{localStorage.setItem(STORAGE,JSON.stringify(state));}catch(e){}}
  function checkDay() {
    if(state.date!==today()) {
      state.date=today();state.day++;state.projects=newProjects(state.day,state.seed);
      state.active=null;save();render();notify('A fresh collection of projects has arrived!');
    }
  }
  function active() {
    return state.projects.find(p=>p.key===state.active&&!p.done)||state.projects.find(p=>!p.done)||null;
  }
  function metadata(project) {return CATALOG.find(item=>item.id===project.id);}
  function select(key) {
    const p=state.projects.find(item=>item.key===key&&!item.done);
    if(!p)return;
    state.active=p.key;save();render();notify('Now building: '+metadata(p).name);
  }
  function percent(p,i) {return p.need[i]===0?1:Math.min(1,p.have[i]/p.need[i]);}
  function progress(p) {
    return p.have.reduce((s,v,i)=>s+Math.min(v,p.need[i]),0)/Math.max(1,p.need.reduce((s,v)=>s+v,0));
  }
  function notify(message) {
    $('toast').textContent=message;$('toast').classList.add('show');
    clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').classList.remove('show'),1900);
  }
  function toss(type) {
    if(!TYPES.includes(type))return false;
    checkDay();const idx=TYPES.indexOf(type);const project=active();
    state.total++;
    lastEvent={type,at:performance.now(),plot:project?.plot??0};
    let gained=false;
    // IMPORTANT: contributions never carry forward to another queued project.
    if(project && project.have[idx]<project.need[idx]) {
      project.have[idx]++;gained=true;
      if(project.have.every((n,i)=>n>=project.need[i])) {
        project.done=true;
        state.completed.push({id:project.id,plot:project.plot,day:state.day});
        notify(metadata(project).name+' completed!');
        state.active=state.projects.find(p=>!p.done)?.key??null;
      }
    } else {state.scenery++;}
    const pt=plotCoords(lastEvent.plot);
    for(let i=0;i<13;i++)particles.push({x:pt.x+(Math.random()-.5)*85,
      y:pt.y-55+Math.random()*45,vx:(Math.random()-.5)*2,vy:-1-Math.random()*2,
      life:1,color:['#fff4c4','#f6d982','#fffbe0'][i%3]});
    if(!gained)notify(type[0].toUpperCase()+type.slice(1)+' +1 · village scenery');
    else if(!project.done)notify(type[0].toUpperCase()+type.slice(1)+' +1');
    save();render();
    const item=document.querySelector(`[data-resource="${type}"]`);
    if(item){item.classList.remove('pulse');void item.offsetWidth;item.classList.add('pulse');}
    return true;
  }
  window.ecoCitySort=toss;
  window.addEventListener('message',event=>{
    if(event.origin===location.origin&&event.data?.kind==='eco-sort')toss(event.data.type);
  });
  function render() {
    const current=active();if(current&&!state.active)state.active=current.key;
    $('dailyCount').textContent=state.projects.filter(p=>p.done).length+' / 8';
    $('resourceGrid').innerHTML=TYPES.map((type,i)=>`
      <div class="resource-item" data-resource="${type}">
        <img src="${assetURL('assets/ui/'+ICON[type]+'.png')}" alt="">
        <div class="resource-info">
          <div class="resource-name">${type[0].toUpperCase()+type.slice(1)}</div>
          <div class="resource-count">${current?current.have[i]+' / '+current.need[i]:'✓'}</div>
          <div class="track"><i style="width:${current?percent(current,i)*100:100}%;background:${COLORS[type]}"></i></div>
        </div>
      </div>`).join('');
    $('dailyList').innerHTML=state.projects.map(p=>{
      const item=metadata(p),v=Math.round(progress(p)*100);
      return `<button type="button" class="daily-entry ${current?.key===p.key?'active':''}"
        data-project="${p.key}" ${p.done?'disabled':''}>
          <img src="${assetURL('assets/'+item.art+'.png')}" alt="">
          <div class="daily-text"><b>${item.name}</b>
           <div class="need-list">${TYPES.map((type,i)=>
             `<span class="need-chip" title="${type}"><img src="${assetURL('assets/ui/'+ICON[type]+'.png')}" alt="${type}">${p.need[i]}</span>`
           ).join('')}</div>
           <div class="track"><i style="width:${v}%"></i></div>
           <div class="daily-status">${p.done?'Completed ✓':current?.key===p.key?'In progress':'Queued'} · ${v}%</div>
          </div></button>`;
    }).join('');
    document.querySelectorAll('[data-project]').forEach(b=>b.addEventListener('click',()=>select(b.dataset.project)));
    const item=current?metadata(current):null;
    $('projectTitle').textContent=item?.name||'The village is flourishing!';
    $('projectDescription').textContent=item?.desc||'Extra resources now beautify the village.';
    $('projectImage').src=assetURL('assets/'+(item?.art||'parks/garden')+'.png');
    const v=current?Math.round(progress(current)*100):100;
    $('currentBar').style.width=v+'%';$('currentPercent').textContent=v+'%';
  }
  // All terrain tiles use the same world-space isometric grid.
  const ROWS=15,COLS=17,TW=100,TH=52,ORIGIN_X=690,ORIGIN_Y=12;
  let MAP_SCALE=.53, MAP_OFFSET_X=255, MAP_OFFSET_Y=236;
  function fitMap() {
    // The visual centre is between the actual left/right UI panels, NOT
    // the centre of the whole screen. Recompute on viewport changes.
    const rect=canvas.getBoundingClientRect();
    const kx=W/Math.max(1,rect.width), ky=H/Math.max(1,rect.height);
    const panelL=document.querySelector('.resources').getBoundingClientRect();
    const panelR=document.querySelector('.daily').getBoundingClientRect();
    const bottom=document.querySelector('.bottom').getBoundingClientRect();
    const left=(panelL.right-rect.left)*kx;
    const right=(panelR.left-rect.left)*kx;
    const margin=22*kx;
    const usable=Math.max(1,right-left-2*margin);
    // The map extends slightly beyond the tile-centre positions because
    // buildings and trees are wider than their anchor points.
    const mapMinX=-105, mapMaxX=1560;
    const mapMinY=-145, mapMaxY=855;
    const bottomLimit=(bottom.top-rect.top)*ky-14*ky;
    const topLimit=85*ky;
    MAP_SCALE=Math.min(.60, usable/(mapMaxX-mapMinX),
                       Math.max(.20,(bottomLimit-topLimit)/(mapMaxY-mapMinY)));
    // Shift the village slightly left of the free area's midpoint; leave
    // enough breathing room for the project's right-hand artwork.
    const center=(left+right)/2-10*kx;
    MAP_OFFSET_X=center-MAP_SCALE*(mapMinX+mapMaxX)/2;
    MAP_OFFSET_Y=topLimit-MAP_SCALE*mapMinY;
  }
  let terrain=[],riverCols=[],plots=[],decor=[];
  function tileCenter(row,col) {return {x:ORIGIN_X+(col-row)*TW/2,y:ORIGIN_Y+(col+row)*TH/2};}
  function generateMap() {
    const random=rng(state.seed);let rc=11;
    riverCols=[];
    for(let row=0;row<ROWS;row++){
      rc=Math.max(8,Math.min(14,rc+(random()<.3?-1:random()>.75?1:0)));
      riverCols.push(rc);
    }
    terrain=[];
    for(let row=0;row<ROWS;row++) {
      terrain[row]=[];
      for(let col=0;col<COLS;col++) {
        const river=Math.abs(col-riverCols[row])<=1;
        terrain[row][col]=river?'river':random()<.11?'path':'grass';
      }
    }
    plots=[];
    const preferred=[[4,5],[7,7],[10,7],[3,8],[11,10],[6,3],[12,5],[8,10],[3,3],[10,3],[13,8],[5,10]];
    for(const [row,col] of preferred) {
      if(terrain[row]?.[col]==='river'||plots.some(p=>Math.abs(p.row-row)<2&&Math.abs(p.col-col)<2))continue;
      const pt=tileCenter(row,col);
      if(pt.x>180&&pt.x<1100&&pt.y>140&&pt.y<710)plots.push({row,col});
      if(plots.length>=8)break;
    }
    const candidates=[];
    for(let row=2;row<ROWS-1;row++)for(let col=2;col<COLS-1;col++){
      const pt=tileCenter(row,col);
      if(terrain[row][col]!=='river'&&pt.x>190&&pt.x<1100&&pt.y>140&&pt.y<730)
        candidates.push({row,col});
    }
    shuffle(candidates,random);
    for(const p of candidates){if(plots.length===8)break;
      if(!plots.some(q=>Math.abs(q.row-p.row)<2&&Math.abs(q.col-p.col)<2))plots.push(p);
    }
    decor=[];
    const trees=['tree_green','tree_cherry','tree_autumn','tree_pine','tree_willow','tree_flower','tree_red'];
    for(let row=0;row<ROWS;row++)for(let col=0;col<COLS;col++){
      if(row<2||col<2||row>ROWS-3||col>COLS-3||terrain[row][col]==='river')continue;
      if(plots.some(p=>Math.abs(p.row-row)<2&&Math.abs(p.col-col)<2))continue;
      const chance=random();
      if(chance<.24)decor.push({row,col,id:'trees/'+trees[Math.floor(random()*trees.length)],size:.77+random()*.33});
      else if(chance<.42)decor.push({row,col,id:random()<.52?'plants/bush_white':'plants/flower_patch_01',size:.71+random()*.33});
    }
  }
  function plotCoords(index) {
    const p=plots[index%Math.max(1,plots.length)]||{row:6,col:5};return tileCenter(p.row,p.col);
  }
  // draw sprites by their bottom-center ground anchor and sort by row+column below.
  function sprite(path,x,y,width,height,glow=0) {
    const im=assets[path];if(!im?.complete||!im.naturalWidth)return;
    ctx.save();
    if(glow){ctx.shadowColor='#ffe297';ctx.shadowBlur=26*glow;}
    ctx.drawImage(im,x-width/2,y-height,width,height);ctx.restore();
  }
  function drawBackground() {
    // Only the background fills the canvas; the village uses fitMap().
    // A full-size (roughly landscape iPad aspect) image looks much better
    // than stretching the 775x67 legacy sky strip into a tall image.
    const chosen=assets['background/'+BACKGROUND_OPTION];
    const fallback=assets['background/full_landscape'];
    const img=(chosen?.complete&&chosen.naturalWidth)?chosen:
              (fallback?.complete&&fallback.naturalWidth)?fallback:null;
    if(img) {
      // Fill the entire canvas with no green bars or short sky strip.
      ctx.drawImage(img,0,0,W,H);
      return;
    }
    ctx.fillStyle='#94a9a1';ctx.fillRect(0,0,W,H);
  }
  function draw() {
    if(!state)return;
    ctx.clearRect(0,0,W,H);drawBackground();
    ctx.save();ctx.translate(MAP_OFFSET_X,MAP_OFFSET_Y);ctx.scale(MAP_SCALE,MAP_SCALE);
    // Draw one diagonal at a time so nearer tiles overlap farther tiles naturally.
    for(let sum=0;sum<ROWS+COLS-1;sum++)for(let row=0;row<ROWS;row++){
      const col=sum-row;if(col<0||col>=COLS)continue;
      const pos=tileCenter(row,col),kind=terrain[row][col];
      let id;
      if(kind==='river')id='water/water_0'+(1+(row+col)%4);
      else if(kind==='path')id='terrain/path_0'+(1+(row+col)%5);
      else id='terrain/grass_0'+(1+(row*3+col)%5);
      // The supplied assets have a ~100x85 canvas with painted isometric edges.
      sprite(id,pos.x,pos.y+42,TW+2,85);
    }
    const scene=[];
    const add=(row,col,layer,fn)=>scene.push({depth:row+col,layer,fn});
    // No free-floating decorative bridge. Bridge art belongs to an earned project.
    for(const d of decor) {
      const pos=tileCenter(d.row,d.col),tree=d.id.startsWith('trees/');
      add(d.row,d.col,2,()=>sprite(d.id,pos.x,pos.y+30,(tree?113:74)*d.size,(tree?135:76)*d.size));
    }
    for(let i=0;i<plots.length;i++) {
      const p=state.projects[i];if(!p)continue;
      const pos=plotCoords(i),site=plots[i],item=metadata(p);
      const build=percent(p,0),plants=percent(p,1),paper=percent(p,2),energy=percent(p,3);
      const stage=Math.min(5,Math.floor(build*5.999));
      const glow=lastEvent?.plot===i?Math.max(0,1-(performance.now()-lastEvent.at)/2600):0;
      add(site.row,site.col,3,()=>{
        if(plants>=.25)sprite('plants/flower_patch_02',pos.x-78,pos.y+38,42,40,lastEvent?.type==='compost'?glow:0);
        if(plants>=.65)sprite('plants/bush_yellow',pos.x+78,pos.y+36,45,40,lastEvent?.type==='compost'?glow:0);
        const art=p.done||build>=1?item.art:'stages/stage'+stage;
        sprite(art,pos.x,pos.y+33,p.done||build>=1?154:140,p.done||build>=1?145:132,lastEvent?.type==='recycling'?glow:0);
        if(paper>=.25)sprite('props/planter',pos.x+78,pos.y+35,35,40,lastEvent?.type==='paper'?glow:0);
        if(paper>=.75)sprite('props/arch_flower',pos.x-85,pos.y+32,51,71,lastEvent?.type==='paper'?glow:0);
        if(energy>=.25)sprite('props/lamp_post',pos.x-86,pos.y+32,29,72,lastEvent?.type==='garbage'?glow:0);
        if(energy>=.7)sprite('props/lamp_post',pos.x+86,pos.y+32,29,72,lastEvent?.type==='garbage'?glow:0);
        if(p.key===active()?.key){ctx.save();ctx.setLineDash([5,5]);ctx.lineWidth=2;ctx.strokeStyle='#ffefb4';ctx.beginPath();ctx.ellipse(pos.x,pos.y+29,77,28,0,0,Math.PI*2);ctx.stroke();ctx.restore();}
      });
    }
    const earlier=state.completed.filter(p=>p.day!==state.day);
    earlier.slice(-4).forEach((p,i)=>{
      const row=3+i*2,col=2+i%2,pos=tileCenter(row,col),item=CATALOG.find(x=>x.id===p.id);
      if(item)add(row,col,3,()=>sprite(item.art,pos.x,pos.y+34,138,129));
    });
    if(state.scenery){const random=rng(state.seed+state.scenery);
      for(let i=0;i<Math.min(state.scenery,24);i++){
        const row=2+Math.floor(random()*11),col=2+Math.floor(random()*11);
        if(terrain[row]?.[col]==='river'||plots.some(p=>Math.abs(p.row-row)<2&&Math.abs(p.col-col)<2))continue;
        const pos=tileCenter(row,col);
        add(row,col,1,()=>sprite('plants/flower_patch_03',pos.x,pos.y+30,43,38));
      }
    }
    scene.sort((a,b)=>a.depth-b.depth||a.layer-b.layer);
    scene.forEach(item=>item.fn());
    ctx.restore();
    for(let i=particles.length-1;i>=0;i--){const p=particles[i];
      ctx.save();ctx.globalAlpha=p.life;ctx.fillStyle=p.color;ctx.shadowColor='#ffe083';ctx.shadowBlur=9;
      ctx.beginPath();ctx.arc(MAP_OFFSET_X+MAP_SCALE*p.x,MAP_OFFSET_Y+MAP_SCALE*p.y,2.8*p.life,0,Math.PI*2);ctx.fill();ctx.restore();
      p.x+=p.vx;p.y+=p.vy;p.life-=.02;if(p.life<=0)particles.splice(i,1);
    }
  }
  function tick(){draw();requestAnimationFrame(tick);}
  document.querySelectorAll('[data-sort]').forEach(b=>b.addEventListener('click',()=>toss(b.dataset.sort)));
  state=load();generateMap();checkDay();save();render();fitMap();requestAnimationFrame(tick);
  window.addEventListener('resize',fitMap);
  setInterval(checkDay,60000);
})();
