// Shared graphic language for the WebGL and CPU globes. These are original
// editorial surfaces, never simulated evidence of an archival capture process.
export const PATTERNS=new Set(['clear','paper','hatch','rays','cutout','halftone','grooves','diagonal','pixels','mosaic','chrome','notation','cinema','spotlight','keys']);
export function paintConceptPattern(ctx,style,palette,width,height){
 if(!style||!PATTERNS.has(style.pattern))return;
 ctx.save();ctx.strokeStyle=palette.line;ctx.fillStyle=palette.line;ctx.globalAlpha=.17;ctx.lineWidth=1;
 const path=(x1,y1,x2,y2)=>{ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke()};
 const unit=width/512;
 ctx.scale(unit,unit);const w=width/unit,h=height/unit;
 switch(style.pattern){
  case 'mosaic':ctx.globalAlpha=1;for(let y=0;y<h;y+=12)for(let x=0;x<w;x+=12){const noise=Math.abs(Math.sin(x*12.91+y*7.31)*43758.55)%1,hue=x<w/2?310:210;ctx.fillStyle=`hsl(${hue} 15% ${11+noise*14}%)`;ctx.fillRect(x+1,y+1,10,10);ctx.strokeStyle='#c5d6e530';ctx.lineWidth=.6;ctx.strokeRect(x+1,y+1,10,10)}break;
  case 'paper':for(let y=9;y<h;y+=14)path(0,y,w,y);ctx.globalAlpha=.09;for(let x=11;x<w;x+=43)path(x,0,x+9,h);break;
  case 'hatch':for(let x=-h;x<w;x+=8)path(x,0,x+h,h);break;
  case 'rays':for(let i=0;i<32;i++){const a=i*Math.PI/16;path(w/2,h/2,w/2+Math.cos(a)*w,h/2+Math.sin(a)*w)}break;
  case 'halftone':for(let y=4;y<h;y+=11)for(let x=4;x<w;x+=11){ctx.beginPath();ctx.arc(x,y,1.9,0,Math.PI*2);ctx.fill()}break;
  case 'grooves':ctx.lineWidth=3;for(let r=18;r<w;r+=17){ctx.beginPath();ctx.ellipse(w/2,h/2,r,r*.65,0,0,Math.PI*2);ctx.stroke()}break;
  case 'diagonal':ctx.lineWidth=10;for(let x=-h;x<w;x+=85)path(x,0,x+h,h);break;
  case 'pixels':for(let y=0;y<h;y+=28)for(let x=0;x<w;x+=28){ctx.strokeRect(x,y,21,21)}break;
  case 'chrome':{const g=ctx.createLinearGradient(0,0,w,h);g.addColorStop(0,'#ffffff');g.addColorStop(.28,'#ffffff00');g.addColorStop(.49,'#ffffff00');g.addColorStop(.51,'#ffffff');g.addColorStop(.6,'#ffffff00');g.addColorStop(1,'#ffffff');ctx.globalAlpha=.35;ctx.fillStyle=g;ctx.fillRect(0,0,w,h);break}
  case 'notation':for(let y=18;y<h;y+=52){for(let j=0;j<5;j++)path(0,y+j*5,w,y+j*5);for(let x=17;x<w;x+=51){ctx.beginPath();ctx.moveTo(x,y+3);ctx.lineTo(x+5,y+8);ctx.lineTo(x,y+13);ctx.lineTo(x-5,y+8);ctx.closePath();ctx.fill()}}break;
  case 'cutout':ctx.fillRect(w*.08,h*.17,w*.16,h*.53);ctx.fillRect(w*.64,h*.57,w*.29,h*.21);break;
  case 'cinema':ctx.lineWidth=4;ctx.strokeRect(15,12,w-30,h-24);for(let x=24;x<w-24;x+=22){ctx.fillRect(x,2,11,5);ctx.fillRect(x,h-7,11,5)}break;
  case 'spotlight':{const g=ctx.createRadialGradient(w*.3,h*.25,4,w*.3,h*.25,w*.32);g.addColorStop(0,'#ffffff');g.addColorStop(1,'#ffffff00');ctx.fillStyle=g;ctx.globalAlpha=.24;ctx.fillRect(0,0,w,h);break}
  case 'keys':for(let x=0;x<w;x+=29){path(x,h*.2,x,h*.8);if(x%87!==0)ctx.fillRect(x-5,h*.2,9,h*.24)}break;
 }
 ctx.restore();
}
export function conceptSurface(style,palette,{opaque=false,width=512,height=256}={}){
 if(!style||!PATTERNS.has(style.pattern))return null;const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;const ctx=canvas.getContext('2d');if(!ctx)return null;if(opaque){ctx.fillStyle=palette.mid;ctx.fillRect(0,0,width,height)}paintConceptPattern(ctx,style,palette,width,height);return canvas;
}
