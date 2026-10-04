/* Trash Royale — shared Pi city game with the uploaded Cozy_Game_Assets.
   The backend owns resources, projects, persistence, and motor events.
   window.ecoCitySort(type) adds the same simulated resource as the +1 buttons.
   All image paths below refer to individual PNGs; no concept-sheet crops are drawn.
*/
(() => {
  'use strict';
  const TYPES = ['recycling', 'compost', 'paper', 'garbage'];
  const ICON = {recycling:'icon_recycling', compost:'icon_compost', paper:'icon_paper', garbage:'icon_garbage'};
  const COLORS = {recycling:'#cb8062', compost:'#839b6c', paper:'#b89d79', garbage:'#e4ad55'};
  const CATALOG = [
    {id:'house', name:'Cozy Cottage', desc:'A little home to welcome new neighbours.', art:'residential/house_cottage'},
    {id:'library', name:'Community Library', desc:'A place for learning, meeting, and growing together.', art:'community/library'},
    {id:'cafe', name:'Corner Café', desc:'A warm cup of something and a friendly place to meet.', art:'community/cafe'},
    {id:'park', name:'Riverside Park', desc:'A leafy retreat beside the gentle river.', art:'parks/park'},
    {id:'school', name:'Village School', desc:'A bright place for curious minds.', art:'community/community_hall'},
    {id:'townhall', name:'Town Hall', desc:'The heart of the village and its celebrations.', art:'community/community_hall'},
    {id:'garden', name:'Community Garden', desc:'Fresh vegetables, flowers, and a shared harvest.', art:'parks/garden'},
    {id:'market', name:'Farmers’ Market', desc:'Local produce and friendly market stalls.', art:'community/market'},
    {id:'bakery', name:'Village Bakery', desc:'A cosy bakery with freshly made treats.', art:'commercial/bakery'},
    {id:'community', name:'Community Centre', desc:'A welcoming space for everyone to gather.', art:'community/community_hall'},
    {id:'clinic', name:'Health Clinic', desc:'A caring place for our neighbours.', art:'commercial/clinic'},
    {id:'studio', name:'Art Studio', desc:'A colourful space for creativity.', art:'community/workshop'},
    {id:'bridge', name:'Riverside Bridge', desc:'A new connection across the water.', art:'bridges_docks/bridge_stone'},
    {id:'playground', name:'Playground', desc:'A place to play, explore, and make friends.', art:'parks/park'},
    {id:'plaza', name:'Solar Plaza', desc:'A sunny gathering place powered by our shared efforts.', art:'parks/gazebo'},
    {id:'bike', name:'Bike Station', desc:'A shared station for a greener journey through the village.', art:'utility/recycling_center'},
    {id:'arts', name:'Arts Pavilion', desc:'A colourful space for creativity.', art:'community/workshop'}
  ];
  const $ = id => document.getElementById(id);
  const canvas = $('village');
  const ctx = canvas.getContext('2d');
  let W = canvas.width, H = canvas.height;
  // Use ?background=sunny|sunset|autumn|evening|misty to preview alternate scenes.
  const BACKGROUND_OPTION = new URLSearchParams(location.search).get('background') || 'full_landscape';
  const assetPaths = new Set([
    'background/full_landscape','background/'+BACKGROUND_OPTION,
    'cliffs/floating_island_rock',
    ...[1,2,3,4,5].map(n => `terrain/grass_0${n}`),
    ...[1,2,3,4,5].map(n => `terrain/path_0${n}`),
    ...[1,2,3,4,5,6,7,8].map(n => `water/water_0${n}`),
    'bridges_docks/bridge_stone','bridges_docks/bridge_wood','props/lamp_post',
    'props/planter','props/arch_flower','props/bench','props/fence_wood',
    'plants/bush_white','plants/bush_yellow','plants/flower_patch_01',
    'plants/flower_patch_02','plants/flower_patch_03','plants/rock_flower',
    'trees/tree_green','trees/tree_cherry','trees/tree_autumn','trees/tree_pine',
    'trees/tree_willow','trees/tree_flower','trees/tree_red',
    ...[0,1,2,3,4,5].map(n => `stages/stage${n}`)
  ]);
  const assetURL=path=>path; // Embedded HTML replaces this with its packaged data URLs.
  const assets = {};
  let assetRevision=0;
  let state = null;
  let needsDraw=true,lastDraw=0,wasAnimating=false;
  function loadAsset(path) {
    if(assets[path])return;
    const im = new Image();
    assets[path] = im;
    im.onload = () => { assetRevision++;needsDraw=true; };
    im.src = assetURL('assets/' + path + '.png');
  }
  assetPaths.forEach(loadAsset);
  function rng(seed) {
    return () => {seed |= 0;seed = seed+0x6D2B79F5|0;
      let x=Math.imul(seed^seed>>>15,1|seed);x=x+Math.imul(x^x>>>7,61|x)^x;
      return ((x^x>>>14)>>>0)/4294967296;};
  }
  function shuffle(list,random) {
    for(let i=list.length-1;i>0;i--){const j=Math.floor(random()*(i+1));[list[i],list[j]]=[list[j],list[i]];}
    return list;
  }
  let particles=[],lastEvent=null,toastTimer;
  let serverState=null,connected=false,busy=false,revision=0,citySignature='';
  const capital=value=>value[0].toUpperCase()+value.slice(1);
  const escapeHTML=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  async function request(path,body) {
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),10000);
    try {
      const response=await fetch(path,{
        method:body===undefined?'GET':'POST',cache:'no-store',signal:controller.signal,
        ...(body===undefined?{}:{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
      });
      const result=await response.json();
      if(!response.ok)throw new Error(result.error||'The sorting bin could not complete that action.');
      return result;
    } finally {clearTimeout(timeout);}
  }
  function projectView(project,plot) {
    return {key:project.id,id:project.kind,name:project.name,plot,
      day:project.id.slice(0,10),need:TYPES.map(type=>project.required[type]),
      have:TYPES.map(type=>project.progress[type]),
      done:TYPES.every(type=>project.progress[type]>=project.required[type])};
  }
  function applyState(snapshot) {
    const previous=state;
    serverState=snapshot;connected=true;
    state={day:snapshot.day,seed:Number(snapshot.map_seed)>>>0,
      projects:snapshot.queue.map(projectView),active:snapshot.active_id,
      completed:snapshot.completed.map(projectView),total:snapshot.correct_sorts,
      scenery:TYPES.reduce((sum,type)=>sum+snapshot.decorations[type],0)};
    [...state.projects,...state.completed].forEach(project=>loadAsset(metadata(project).art));
    if(!previous||previous.seed!==state.seed){
      generateMap();
      particles=[];lastEvent=null;
      fittedView=null;fitMap();
      if(previous)notify('A new village is ready!');
    }
    const signature=JSON.stringify(state);
    if(signature!==citySignature){citySignature=signature;render();needsDraw=true;}
    if(previous&&previous.day!==state.day)notify('A fresh collection of projects has arrived!');
    if(previous&&state.total>previous.total){
      const event=snapshot.history.find(item=>item.correct);
      if(event)celebrate(event,previous);
    } else if(previous&&snapshot.history[0]&&!snapshot.history[0].correct&&
              snapshot.history[0].time!==previous.lastHistoryTime) {
      notify('That sort earned no resource. Try again with the next item.');
    }
    state.lastHistoryTime=snapshot.history[0]?.time;
    updateControls();
  }
  function updateControls() {
    const pending=serverState?.pending,motor=serverState?.motor;
    const demo=serverState?.mode==='demo';
    $('binPanel').hidden=!!serverState&&demo&&connected&&!pending&&!serverState.error;
    $('binMode').textContent=demo?'Demo sorting':'Sorting bin';
    $('binStatus').textContent=connected?serverState.status:
      serverState?'Connection lost. Reconnecting…':'Connecting to the village…';
    $('pendingItem').hidden=!pending;
    $('pendingItem').textContent=pending?pending.item+' · '+capital(pending.label):'';
    $('binError').hidden=!serverState?.error;
    $('binError').textContent=serverState?.error||'';
    $('sortHint').textContent=motor?.faulted?'Check the gates and restart the bin.':
      motor?.enabled?'Items add resources after automatic routing.':
      pending?'Confirm the actual bin below. The +1 buttons add demo resources.':
      demo?'Tap a category to try a sort.':'Place one item in the sorting area. The +1 buttons add demo resources.';
    document.querySelectorAll('[data-sort]').forEach(button=>{
      button.disabled=!connected||busy;
      button.title='Add one demo '+button.dataset.sort+' resource';
    });
    $('confirmBins').hidden=!pending||!!motor?.enabled;
    document.querySelectorAll('[data-confirm-bin]').forEach(button=>{
      button.disabled=!connected||busy||!pending||!!motor?.enabled;
    });
    document.querySelectorAll('[data-project]').forEach(button=>{
      button.disabled=!connected||busy||state.projects.find(p=>p.key===button.dataset.project)?.done;
    });
    $('dismissItem').hidden=!pending||motor?.routing;
    $('dismissItem').disabled=!connected||busy;
    $('resetScene').hidden=!serverState||demo;
    $('resetScene').disabled=!connected||busy||!!pending||serverState?.classifying||motor?.routing||motor?.faulted;
    $('binActions').hidden=$('dismissItem').hidden&&$('resetScene').hidden;
    $('resetGame').disabled=!connected||busy||serverState?.classifying||motor?.routing;
  }
  async function refresh() {
    if(busy)return;
    const started=revision;
    try {
      const snapshot=await request('/api/state');
      if(started===revision)applyState(snapshot);
    } catch(error) {
      if(started===revision){connected=false;updateControls();}
    }
  }
  async function act(path,body) {
    if(busy||!connected)return false;
    busy=true;revision++;updateControls();
    try {
      const result=await request(path,body);
      applyState(result.state||result);
      return true;
    } catch(error) {
      notify(error.name==='AbortError'?'The bin took too long to respond. Reconnecting…':error.message);
      return false;
    } finally {
      busy=false;updateControls();
      // Reconcile even when a response was lost; never retry a resource POST.
      await refresh();
    }
  }
  function active() {
    return state?.projects.find(p=>p.key===state.active&&!p.done)||state?.projects.find(p=>!p.done)||null;
  }
  function metadata(project) {
    const item=CATALOG.find(item=>item.id===project.id)||CATALOG.find(item=>item.id==='garden');
    return {...item,name:project.name||item.name};
  }
  async function select(key) {
    const p=state.projects.find(item=>item.key===key&&!item.done);
    if(!p)return;
    if(await act('/api/project',{id:key}))notify('Now building: '+metadata(p).name);
  }
  function percent(p,i) {return p.need[i]===0?1:Math.min(1,p.have[i]/p.need[i]);}
  function progress(p) {
    return p.have.reduce((s,v,i)=>s+Math.min(v,p.need[i]),0)/Math.max(1,p.need.reduce((s,v)=>s+v,0));
  }
  function notify(message) {
    $('toast').textContent=message;$('toast').classList.add('show');
    clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').classList.remove('show'),1900);
  }
  async function toss(type) {
    if(!TYPES.includes(type))return false;
    return act('/api/demo_sort',{category:type});
  }
  async function confirmBin(type) {
    if(!TYPES.includes(type)||!serverState?.pending||serverState.motor.enabled)return false;
    return act('/api/confirm',{bin:type});
  }
  function celebrate(event,previous) {
    const type=event.predicted;
    const project=state.projects.find(p=>p.name===event.project);
    lastEvent={type,at:performance.now(),plot:project?.plot??0};
    needsDraw=true;
    const pt=plotCoords(lastEvent.plot);
    for(let i=0;i<13;i++)particles.push({x:pt.x+(Math.random()-.5)*85,
      y:pt.y-55+Math.random()*45,vx:(Math.random()-.5)*2,vy:-1-Math.random()*2,
      life:1,color:['#fff4c4','#f6d982','#fffbe0'][i%3]});
    if(!project)notify(capital(type)+' +1 · village scenery');
    else if(project.done&&!previous.projects.find(p=>p.key===project.key)?.done)
      notify(metadata(project).name+' completed!');
    else notify(capital(type)+' +1');
    const item=document.querySelector(`[data-resource="${type}"]`);
    if(item){item.classList.remove('pulse');void item.offsetWidth;item.classList.add('pulse');}
  }
  window.ecoCitySort=toss;
  window.addEventListener('message',event=>{
    if(event.origin===location.origin&&event.data?.kind==='eco-sort')toss(event.data.type);
  });
  function render() {
    const current=active();
    $('dailyCount').textContent=state.projects.filter(p=>p.done).length+' / '+state.projects.length;
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
        data-project="${escapeHTML(p.key)}" ${p.done?'disabled':''}>
          <img src="${assetURL('assets/'+item.art+'.png')}" alt="">
          <div class="daily-text"><b>${escapeHTML(item.name)}</b>
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
  const ISLAND_DEPTH=570;
  const reducedMotion=window.matchMedia('(prefers-reduced-motion: reduce)');
  let mapVisible=true;
  let MAP_SCALE=.53, MAP_OFFSET_X=255, MAP_OFFSET_Y=236;
  let fittedView=null;
  const navigation=window.attachMapNavigation(canvas,{
    getScaleLimits:()=>({minScale:(fittedView?.scale||.5)*.25,maxScale:(fittedView?.scale||.5)*4}),
    getView:()=>({scale:MAP_SCALE,x:MAP_OFFSET_X,y:MAP_OFFSET_Y}),
    setView:view=>{
      MAP_SCALE=view.scale;MAP_OFFSET_X=view.x;MAP_OFFSET_Y=view.y;needsDraw=true;
    }
  });
  function fitMap() {
    // Size the backing canvas to the map's grid area so one world scale keeps
    // both island faces, sprites, and particles in proportion at every ratio.
    const rect=canvas.getBoundingClientRect();
    const width=Math.max(1,rect.width),height=Math.max(1,rect.height);
    const density=Math.min(window.devicePixelRatio||1,2,Math.sqrt(2500000/(width*height)));
    W=Math.max(1,Math.round(width*density));H=Math.max(1,Math.round(height*density));
    if(canvas.width!==W)canvas.width=W;
    if(canvas.height!==H)canvas.height=H;
    const mapMinX=-150,mapMaxX=1740,mapMinY=-65,mapMaxY=islandTip.y+220;
    const padding=Math.min(24,Math.min(width,height)*.04)*density;
    const scale=Math.min((W-2*padding)/(mapMaxX-mapMinX),(H-2*padding)/(mapMaxY-mapMinY));
    const nextFit={scale,x:W/2-scale*(mapMinX+mapMaxX)/2,y:H/2-scale*(mapMinY+mapMaxY)/2};
    if(fittedView){
      const ratio=nextFit.scale/fittedView.scale;
      MAP_SCALE=nextFit.scale*Math.max(.25,Math.min(4,MAP_SCALE/fittedView.scale));
      MAP_OFFSET_X=nextFit.x+(MAP_OFFSET_X-fittedView.x)*ratio;
      MAP_OFFSET_Y=nextFit.y+(MAP_OFFSET_Y-fittedView.y)*ratio;
    } else {
      MAP_SCALE=nextFit.scale;MAP_OFFSET_X=nextFit.x;MAP_OFFSET_Y=nextFit.y;
    }
    fittedView=nextFit;navigation.resetInteraction();needsDraw=true;
  }
  let terrain=[],riverCols=[],plots=[],decor=[];
  function tileCenter(row,col) {return {x:ORIGIN_X+(col-row)*TW/2,y:ORIGIN_Y+(col+row)*TH/2};}
  // The rock rim is derived from the same outer tile anchors as the land.
  // Its small overlap is concealed by the terrain's painted soil edges.
  const islandLeft={...tileCenter(ROWS-1,0)};
  islandLeft.x-=TW*.45;islandLeft.y+=1;
  const islandFront={...tileCenter(ROWS-1,COLS-1)};
  islandFront.y+=32;
  const islandRight={...tileCenter(0,COLS-1)};
  islandRight.x+=TW*.45;islandRight.y+=1;
  const islandTip={x:islandFront.x,y:islandFront.y+ISLAND_DEPTH};
  const islandEffects=window.createIslandEffects({
    rows:ROWS,cols:COLS,tileWidth:TW,tileHeight:TH,tileCenter,islandDepth:ISLAND_DEPTH
  });
  const islandFragments=[
    {x:islandLeft.x-32,y:islandLeft.y+270,size:19,phase:.7},
    {x:islandRight.x+60,y:islandRight.y+400,size:23,phase:2.5},
    {x:islandTip.x+92,y:islandTip.y+94,size:26,phase:4.1}
  ];
  let islandSurface=null,islandSurfaceTextured=false;
  const islandBounds={
    x:Math.floor(islandLeft.x),y:Math.floor(islandLeft.y),
    width:Math.ceil(islandRight.x-islandLeft.x),
    height:Math.ceil(islandTip.y-islandLeft.y)
  };
  function islandFace(edge,reverse=false) {
    const side=reverse?1:-1;
    const width=Math.abs(islandFront.x-edge.x);
    // A narrowing, irregular silhouette reads as suspended rock, rather than a slab.
    const lower=[
      {x:edge.x-side*width*.045,y:edge.y+ISLAND_DEPTH*.26},
      {x:edge.x-side*width*.13,y:edge.y+ISLAND_DEPTH*.55},
      {x:edge.x-side*width*.15,y:edge.y+ISLAND_DEPTH*.53},
      {x:edge.x-side*width*.31,y:edge.y+(islandFront.y-edge.y)*.34+ISLAND_DEPTH*.60},
      {x:edge.x-side*width*.35,y:edge.y+(islandFront.y-edge.y)*.34+ISLAND_DEPTH*.57},
      {x:edge.x-side*width*.57,y:edge.y+(islandFront.y-edge.y)*.62+ISLAND_DEPTH*.80},
      {x:edge.x-side*width*.60,y:edge.y+(islandFront.y-edge.y)*.62+ISLAND_DEPTH*.77},
      {x:edge.x-side*width*.81,y:edge.y+(islandFront.y-edge.y)*.85+ISLAND_DEPTH*.93},
      {x:edge.x-side*width*.85,y:edge.y+(islandFront.y-edge.y)*.85+ISLAND_DEPTH*.90}
    ];
    return [edge,islandFront,islandTip,...lower.reverse()];
  }
  function drawRockDetails(surface,edge,dark) {
    const random=rng(dark?7419:5191);
    const along=u=>({x:edge.x+(islandFront.x-edge.x)*u,y:edge.y+(islandFront.y-edge.y)*u});
    // Small stone ledges, pockets, and mineral flecks give the deeper faces scale.
    for(let i=0;i<22;i++){
      const u=.09+random()*.84,anchor=along(u);
      const depth=(.05+random()*.54)*ISLAND_DEPTH*(.4+u*.6);
      const x=Math.round(anchor.x),y=Math.round(anchor.y+depth);
      const width=9+Math.floor(random()*24),height=5+Math.floor(random()*14);
      surface.fillStyle=dark?'#493e455c':'#71504450';
      surface.fillRect(x-width/2,y,width,height);
      surface.fillStyle=dark?'#b29c716e':'#f0d3a47d';
      surface.fillRect(x-width/2-3,y-3,width+5,3);
      if(i%3===0){surface.fillStyle='#badbd888';surface.fillRect(x+2,y+height-3,3,5);}
    }
    // Moss grows along the soil seam and sends distinct leafy tendrils down the rock.
    for(let i=0;i<13;i++){
      const u=.065+i*.07+(random()-.5)*.028,anchor=along(u);
      const length=(74+random()*ISLAND_DEPTH*.29)*(.65+u*.58);
      const phase=random()*Math.PI*2,rootX=Math.round(anchor.x),rootY=Math.round(anchor.y+5);
      for(let n=0;n<11;n++){
        const x=rootX+Math.floor((random()-.5)*48),y=rootY+Math.floor(random()*16);
        surface.fillStyle=['#334d38','#506c40','#708449','#9ca563'][n%4];
        surface.fillRect(x,y,5+Math.floor(random()*11),3+Math.floor(random()*7));
      }
      const strands=i%3===0?3:2;
      for(let strand=0;strand<strands;strand++){
        const strandLength=length*(1-strand*.19);
        const originX=rootX+(strand-1)*11;
        for(let d=0;d<strandLength;d+=6){
          const x=Math.round(originX+Math.sin(d*.038+phase+strand)*7+Math.sin(d*.016)*4);
          const y=Math.round(rootY+d);
          surface.fillStyle='#304834';surface.fillRect(x+1,y+2,3,8);
          surface.fillStyle=dark?'#557443':'#627f47';surface.fillRect(x,y,2,7);
          if(d%12===0){
            const direction=(d/12+strand)%2?-1:1;
            surface.fillStyle='#354f36';surface.fillRect(x+direction*5-3,y+2,9,6);
            surface.fillStyle=['#6c8b48','#93a35b','#54753f'][Math.floor(d/12)%3];
            surface.fillRect(x+direction*5-2,y,7,5);
            surface.fillStyle='#b6bc715e';surface.fillRect(x+direction*5,y,3,2);
          }
          if(i%5===0&&strand===0&&d%42===0){
            surface.fillStyle='#dbb1b9';surface.fillRect(x-4,y,4,4);
            surface.fillStyle='#f3d5bc';surface.fillRect(x-3,y+1,2,2);
          }
        }
      }
    }
  }
  function drawFloatingIsland() {
    const rock=assets['cliffs/floating_island_rock'];
    const ready=!!(rock?.complete&&rock.naturalWidth);
    if(!islandSurface||ready!==islandSurfaceTextured){
      // Cache both faces in world coordinates; camera gestures only transform this layer.
      islandSurface=document.createElement('canvas');
      islandSurface.width=islandBounds.width;islandSurface.height=islandBounds.height;
      const surface=islandSurface.getContext('2d');
      surface.translate(-islandBounds.x,-islandBounds.y);
      surface.imageSmoothingEnabled=false;
      for(const [edge,dark] of [[islandLeft,false],[islandRight,true]]){
        const points=islandFace(edge,dark);
        surface.save();surface.beginPath();
        points.forEach((point,i)=>i?surface.lineTo(point.x,point.y):surface.moveTo(point.x,point.y));
        surface.closePath();surface.clip();
        surface.fillStyle=dark?'#826653':'#ba9266';
        surface.fillRect(islandBounds.x,islandBounds.y,islandBounds.width,islandBounds.height);
        if(ready){
          surface.save();
          // Project the texture's top edge along the corresponding isometric land edge.
          surface.transform((islandFront.x-edge.x)/rock.naturalWidth,
                            (islandFront.y-edge.y)/rock.naturalWidth,
                            0,(ISLAND_DEPTH+80)/rock.naturalHeight,edge.x,edge.y);
          surface.drawImage(rock,0,0);surface.restore();
        }
        const shade=surface.createLinearGradient(edge.x,edge.y,islandTip.x,islandTip.y);
        shade.addColorStop(0,dark?'#40364338':'#ffe5ad10');
        shade.addColorStop(.65,dark?'#47384765':'#60453a18');
        shade.addColorStop(1,'#3f354966');
        surface.fillStyle=shade;
        surface.fillRect(islandBounds.x,islandBounds.y,islandBounds.width,islandBounds.height);
        drawRockDetails(surface,edge,dark);
        surface.restore();
      }
      islandSurfaceTextured=ready;
    }
    ctx.save();ctx.imageSmoothingEnabled=false;
    ctx.drawImage(islandSurface,islandBounds.x,islandBounds.y);ctx.restore();
  }
  let terrainSurface=null,terrainRevision=-1;
  const terrainBounds={
    x:tileCenter(ROWS-1,0).x-TW/2-4,y:ORIGIN_Y-45,
    width:(ROWS+COLS-2)*TW/2+TW+8,height:(ROWS+COLS-2)*TH/2+90
  };
  function drawTerrain() {
    if(!terrainSurface||terrainRevision!==assetRevision){
      terrainSurface=document.createElement('canvas');
      terrainSurface.width=terrainBounds.width;terrainSurface.height=terrainBounds.height;
      const surface=terrainSurface.getContext('2d');
      surface.translate(-terrainBounds.x,-terrainBounds.y);
      // Build in diagonal order once; water and particles can animate over this cache.
      for(let sum=0;sum<ROWS+COLS-1;sum++)for(let row=0;row<ROWS;row++){
        const col=sum-row;if(col<0||col>=COLS)continue;
        const pos=tileCenter(row,col),kind=terrain[row][col];
        const id=kind==='river'?'water/water_0'+(1+(row+col)%4):
          kind==='path'?'terrain/path_0'+(1+(row+col)%5):
          'terrain/grass_0'+(1+(row*3+col)%5);
        const image=assets[id];
        if(image?.complete&&image.naturalWidth)
          surface.drawImage(image,pos.x-(TW+2)/2,pos.y-43,TW+2,85);
      }
      terrainRevision=assetRevision;
    }
    ctx.save();ctx.imageSmoothingEnabled=false;
    ctx.drawImage(terrainSurface,terrainBounds.x,terrainBounds.y);ctx.restore();
  }
  function drawFloatingFragments(time) {
    for(const fragment of islandFragments){
      const s=fragment.size;
      ctx.save();ctx.translate(fragment.x,fragment.y+Math.sin(time*.65+fragment.phase)*9);
      ctx.fillStyle='#765d55';ctx.beginPath();
      ctx.moveTo(-s,-s*.2);ctx.lineTo(-s*.67,s*.56);ctx.lineTo(0,s*1.13);
      ctx.lineTo(s*.5,s*.68);ctx.lineTo(s,s*.05);ctx.lineTo(s*.68,-s*.39);ctx.closePath();ctx.fill();
      ctx.fillStyle='#b18b63';ctx.beginPath();ctx.moveTo(-s,-s*.2);
      ctx.lineTo(-s*.24,-s*.55);ctx.lineTo(s*.68,-s*.39);ctx.lineTo(s,s*.05);
      ctx.lineTo(0,s*.34);ctx.closePath();ctx.fill();
      ctx.fillStyle='#d1ac77';ctx.beginPath();ctx.moveTo(-s,-s*.2);
      ctx.lineTo(0,s*.34);ctx.lineTo(0,s*1.13);ctx.lineTo(-s*.67,s*.56);ctx.closePath();ctx.fill();
      ctx.fillStyle='#759050';ctx.fillRect(-s*.5,-s*.39,s*.53,5);
      ctx.fillStyle='#a8af65';ctx.fillRect(-s*.3,-s*.44,s*.24,3);
      ctx.restore();
    }
  }
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
    terrainSurface=null;islandEffects.configure(terrain,state.seed);
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
    // The landscape covers the page in CSS; this canvas belongs to the map.
    const chosen=assets['background/'+BACKGROUND_OPTION];
    const fallback=assets['background/full_landscape'];
    const img=(chosen?.complete&&chosen.naturalWidth)?chosen:
              (fallback?.complete&&fallback.naturalWidth)?fallback:null;
    if(img) {
      $('app').style.backgroundImage=`url("${img.src}")`;
      return;
    }
  }
  function draw(now) {
    ctx.clearRect(0,0,W,H);drawBackground();
    if(!state)return;
    ctx.save();ctx.translate(MAP_OFFSET_X,MAP_OFFSET_Y);ctx.scale(MAP_SCALE,MAP_SCALE);
    const time=reducedMotion.matches?0:now/1000;
    islandEffects.drawRear(ctx,time);
    drawFloatingIsland();
    drawTerrain();islandEffects.drawFront(ctx,time);
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
      const row=3+i*2,col=2+i%2,pos=tileCenter(row,col),item=metadata(p);
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
    drawFloatingFragments(time);
    islandEffects.drawParticles(ctx,time);
    ctx.restore();
    for(let i=particles.length-1;i>=0;i--){const p=particles[i];
      ctx.save();ctx.globalAlpha=p.life;ctx.fillStyle=p.color;ctx.shadowColor='#ffe083';ctx.shadowBlur=9;
      ctx.beginPath();ctx.arc(MAP_OFFSET_X+MAP_SCALE*p.x,MAP_OFFSET_Y+MAP_SCALE*p.y,2.8*p.life,0,Math.PI*2);ctx.fill();ctx.restore();
      p.x+=p.vx;p.y+=p.vy;p.life-=.02;if(p.life<=0)particles.splice(i,1);
    }
  }
  function tick(now){
    // Keep atmospheric effects modest on the Pi; all static terrain is cached.
    const atmosphere=state&&!reducedMotion.matches;
    const animating=atmosphere||particles.length>0||(lastEvent&&now-lastEvent.at<2600);
    if(!document.hidden&&mapVisible&&(needsDraw||animating||wasAnimating)&&now-lastDraw>=1000/24){
      draw(now);needsDraw=false;lastDraw=now;wasAnimating=animating;
    }
    requestAnimationFrame(tick);
  }
  document.querySelectorAll('[data-sort]').forEach(b=>b.addEventListener('click',()=>toss(b.dataset.sort)));
  document.querySelectorAll('[data-confirm-bin]').forEach(b=>b.addEventListener('click',()=>confirmBin(b.dataset.confirmBin)));
  $('dismissItem').addEventListener('click',()=>act('/api/dismiss',{}));
  $('resetScene').addEventListener('click',()=>act('/api/reset_scene',{}));
  $('resetGame').addEventListener('click',()=>{
    $('resetGameDialog').returnValue='';
    $('resetGameDialog').showModal();
  });
  $('resetGameDialog').addEventListener('close',async()=>{
    if($('resetGameDialog').returnValue==='reset'&&await act('/api/reset_game',{}))
      notify('Game reset · your new village is ready!');
  });
  fitMap();requestAnimationFrame(tick);
  window.addEventListener('resize',fitMap);
  const layoutObserver=new ResizeObserver(fitMap);
  layoutObserver.observe($('villageStage'));
  const visibilityObserver=new IntersectionObserver(entries=>{
    mapVisible=entries[0].isIntersecting;needsDraw=true;
  });
  visibilityObserver.observe(canvas);
  reducedMotion.addEventListener('change',()=>{needsDraw=true;});
  document.addEventListener('visibilitychange',()=>{needsDraw=true;});
  document.fonts.ready.then(fitMap);
  async function poll(){await refresh();setTimeout(poll,1000);}
  poll();
})();
