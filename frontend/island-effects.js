/* World-space waterfall and atmosphere layers for the floating village. */
(() => {
  'use strict';

  window.createIslandEffects = ({rows,cols,tileWidth,tileHeight,tileCenter,islandDepth}) => {
    let falls=[],motes=[];
    const TAU=Math.PI*2;
    const mix=(a,b,t)=>a+(b-a)*t;
    const fract=value=>value-Math.floor(value);
    function seeded(seed) {
      return () => {
        seed=(seed+0x6D2B79F5)|0;
        let value=Math.imul(seed^seed>>>15,1|seed);
        value^=value+Math.imul(value^value>>>7,61|value);
        return ((value^value>>>14)>>>0)/4294967296;
      };
    }

    function riverRuns(terrain,row) {
      const runs=[];
      for(let col=0;col<cols;col++) {
        if(terrain[row]?.[col]!=='river')continue;
        const start=col;
        while(col+1<cols&&terrain[row]?.[col+1]==='river')col++;
        runs.push({start,end:col});
      }
      return runs;
    }

    function configure(terrain,seed) {
      const random=seeded((Number(seed)^0x6c8e9cf5)>>>0);
      falls=[];
      for(const [row,rear] of [[0,true],[rows-1,false]]) {
        for(const run of riverRuns(terrain,row)) {
          const center=tileCenter(row,(run.start+run.end)/2);
          const count=run.end-run.start+1;
          falls.push({
            rear,
            // The lip follows the tile boundary, including its isometric slope.
            x:center.x+(rear?1:-1)*tileWidth*.25,
            y:center.y+(rear?-tileHeight*.25:tileHeight*.25)+8,
            spanX:count*tileWidth*.5,
            spanY:count*tileHeight*.5,
            height:islandDepth+(rear?430:240),
            drift:rear?0:-tileWidth*.18,
            phase:random()*TAU,
            streaks:Array.from({length:10},()=>({u:.07+random()*.86,phase:random(),speed:.22+random()*.20,length:.055+random()*.11,width:1.2+random()*2.5})),
            drops:Array.from({length:8},()=>({u:random(),phase:random(),speed:.18+random()*.16,size:1.1+random()*1.8})),
            mist:Array.from({length:7},()=>({phase:random(),speed:.09+random()*.08,x:(random()-.5)*1.5,size:8+random()*10}))
          });
        }
      }
      const front=tileCenter(rows-1,cols-1);
      const left=tileCenter(rows-1,0);
      const right=tileCenter(0,cols-1);
      motes=Array.from({length:26},(_,index)=>({
        x:mix(left.x-45,right.x+45,.08+random()*.84),
        y:mix(Math.min(left.y,right.y),front.y+islandDepth,.12+random()*.85),
        drift:18+random()*40,
        bob:8+random()*22,
        phase:random()*TAU,
        speed:.12+random()*.17,
        size:index%6===0?4+random()*2:1.2+random()*1.6,
        leaf:index%6===0,
        color:index%3===0?'#f9e7a0':index%3===1?'#dff2c1':'#f6f9d5'
      }));
    }

    function point(fall,u,v,time=0) {
      // Rear water columns fall vertically from the river lip; only the spray disperses.
      const width=fall.rear?1:1-v*.18;
      const ripple=fall.rear?0:Math.sin(fall.phase+u*TAU*2+v*5+time*1.2)*v*3;
      return {
        x:fall.x+(u-.5)*fall.spanX*width+fall.drift*v+ripple,
        y:fall.y+(u-.5)*fall.spanY+fall.height*v
      };
    }

    function sheetPath(ctx,fall,u0,u1,time) {
      const first=point(fall,u0,0,time);
      ctx.beginPath();ctx.moveTo(first.x,first.y-5);
      const top=point(fall,u1,0,time);ctx.lineTo(top.x,top.y-5);
      for(let step=1;step<=8;step++) {
        const p=point(fall,u1,step/8,time);ctx.lineTo(p.x,p.y);
      }
      for(let step=8;step>=1;step--) {
        const p=point(fall,u0,step/8,time);ctx.lineTo(p.x,p.y);
      }
      ctx.closePath();
    }

    function drawWaterfall(ctx,fall,time) {
      ctx.save();
      const bottom=point(fall,.5,1,time);
      const gradient=ctx.createLinearGradient(fall.x,fall.y,bottom.x,bottom.y);
      gradient.addColorStop(0,'#70d6e3ec');
      gradient.addColorStop(.10,'#7cdcebf0');
      gradient.addColorStop(.42,'#8cdce4c4');
      gradient.addColorStop(.77,'#beedf484');
      gradient.addColorStop(.94,'#d5f7f32b');
      gradient.addColorStop(1,'#d5f7f300');
      sheetPath(ctx,fall,0,1,time);ctx.fillStyle=gradient;ctx.fill();

      // Varied translucent strands keep the water from reading as a solid wall.
      for(const [u0,u1,color] of [[.03,.18,'#eefeff55'],[.28,.43,'#d9f9ff70'],[.57,.75,'#39a9cd55'],[.86,.97,'#eaffff6a']]) {
        const strand=ctx.createLinearGradient(fall.x,fall.y,bottom.x,bottom.y);
        strand.addColorStop(0,color);strand.addColorStop(.70,color);
        strand.addColorStop(1,color.slice(0,7)+'00');
        sheetPath(ctx,fall,u0,u1,time);ctx.fillStyle=strand;ctx.fill();
      }

      // Rolling foam overlaps the painted soil skirt and hides the contact seam.
      const a=point(fall,0,0,time),b=point(fall,1,0,time);
      ctx.lineCap='round';ctx.lineJoin='round';
      ctx.strokeStyle='#e5ffffbc';ctx.lineWidth=8;
      ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();
      ctx.strokeStyle='#ffffffdd';ctx.lineWidth=2.7;
      ctx.beginPath();
      for(let i=0;i<=16;i++) {
        const u=i/16,p=point(fall,u,0,time);
        const y=p.y+Math.sin(u*TAU*3-time*2+fall.phase)*2;
        i?ctx.lineTo(p.x,y):ctx.moveTo(p.x,y);
      }
      ctx.stroke();

      for(const streak of fall.streaks) {
        const progress=fract(streak.phase+time*streak.speed);
        const v0=progress*.98,v1=Math.min(1,v0+streak.length);
        const a=point(fall,streak.u,v0,time),b=point(fall,streak.u,v1,time);
        const mid=point(fall,streak.u,(v0+v1)/2,time);
        ctx.globalAlpha=Math.sin(progress*Math.PI)*.58;
        ctx.strokeStyle='#f4ffff';ctx.lineWidth=streak.width;
        ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.quadraticCurveTo(mid.x,mid.y,b.x,b.y);ctx.stroke();
      }
      for(const drop of fall.drops) {
        const progress=fract(drop.phase+time*drop.speed);
        const p=point(fall,drop.u,.15+progress*.85,time);
        const side=drop.u<.5?-1:1;
        p.x+=side*(5+progress*18);
        ctx.globalAlpha=Math.sin(progress*Math.PI)*.70;
        ctx.fillStyle='#e8ffff';
        ctx.beginPath();ctx.ellipse(p.x,p.y,drop.size,drop.size*2.5,0,0,TAU);ctx.fill();
      }

      // Mist disperses into the sky instead of ending at a rectangular pool.
      for(const puff of fall.mist) {
        const progress=fract(puff.phase+time*puff.speed);
        const p=point(fall,.5,.87,time);
        const radius=puff.size*(.7+progress*1.3);
        const x=p.x+puff.x*fall.spanX*(.35+progress*.65);
        const y=p.y+progress*70;
        ctx.globalAlpha=Math.sin(progress*Math.PI)*.14;
        ctx.fillStyle='#eafffa';
        ctx.beginPath();ctx.ellipse(x,y,radius*2,radius,0,0,TAU);ctx.fill();
      }
      ctx.restore();
    }

    function drawRear(ctx,timeSeconds) {
      for(const fall of falls)if(fall.rear)drawWaterfall(ctx,fall,timeSeconds);
    }
    function drawFront(ctx,timeSeconds) {
      for(const fall of falls)if(!fall.rear)drawWaterfall(ctx,fall,timeSeconds);
    }
    function drawParticles(ctx,timeSeconds) {
      ctx.save();
      for(const mote of motes) {
        const angle=mote.phase+timeSeconds*mote.speed;
        const x=mote.x+Math.sin(angle)*mote.drift;
        const y=mote.y+Math.cos(angle*.73)*mote.bob;
        const alpha=.25+(Math.sin(angle*1.9)+1)*.21;
        ctx.globalAlpha=alpha;
        if(mote.leaf) {
          ctx.save();ctx.translate(x,y);ctx.rotate(angle*.65);
          ctx.fillStyle='#a4bb67';
          ctx.beginPath();ctx.ellipse(0,0,mote.size,mote.size*.40,0,0,TAU);ctx.fill();
          ctx.strokeStyle='#536e45';ctx.lineWidth=.65;
          ctx.beginPath();ctx.moveTo(-mote.size*.7,0);ctx.lineTo(mote.size*.7,0);ctx.stroke();ctx.restore();
        } else {
          ctx.fillStyle=mote.color;
          ctx.beginPath();ctx.arc(x,y,mote.size,0,TAU);ctx.fill();
        }
      }
      ctx.restore();
    }
    return {configure,drawRear,drawFront,drawParticles};
  };
})();
