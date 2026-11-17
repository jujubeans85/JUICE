(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const html = x => String(x).replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  const seed=JSON.parse($("seed").textContent);
  const textFields=["person","title","issue","greeting","note","sender","work","credit","url"];
  const limits=[42,34,34,65,250,36,76,64,512];
  const key="jc-postcards:v1:"+seed.key;
  const defs=[
    {id:"floppy",label:"Floppy disk",w:70,h:42,x:15,y:48},
    {id:"cd",label:"CD sleeve",w:96,h:45,x:98,y:48},
    {id:"record",label:"Record sleeve",w:95,h:58,x:15,y:114},
    {id:"usb",label:"USB tag",w:66,h:29,x:128,y:114},
    {id:"found",label:"Found object",w:76,h:38,x:15,y:194}
  ];
  const corners='<i class="corn tl"></i><i class="corn tr"></i><i class="corn bl"></i><i class="corn br"></i>';
  const rawSeed=Object.fromEntries([...textFields,"art","printArt"].map(k=>[k,seed[k]]));
  const defaultPaper="#efe6cf";
  function allowedUrl(value) {
    const u=new URL(value);
    if(u.protocol!=="https:" || u.username || u.password || u.href.length>512) throw Error("Use a direct HTTPS destination up to 512 characters.");
    return u.href;
  }
  function validArt(s) {
    return typeof s==="string" && (/^data:image\/(?:jpeg|png|webp|gif);base64,[A-Za-z0-9+/=]+$/.test(s) || s==="coast.jpg" || s==="coast-print.jpg");
  }
  function acceptable(d) {
    if(!d||typeof d!=="object"||!textFields.every((k,i)=>typeof d[k]==="string" && d[k].trim() && d[k].length<=limits[i]))return false;
    try{return !!allowedUrl(d.url)&&validArt(d.art)&&validArt(d.printArt);}catch{return false;}
  }
  let editions=[{id:"first",decision:"",...rawSeed}], current="first", front=true;
  try {
    const saved=JSON.parse(localStorage.getItem(key));
    if(saved && Array.isArray(saved.editions)){
      const valid=saved.editions.map(e=>({...e,art:e.art==="@default"?rawSeed.art:e.art,printArt:e.printArt==="@default"?rawSeed.printArt:e.printArt})).filter(e=>acceptable(e)&&typeof e.id==="string"&&["","Yes","No"].includes(e.decision));
      if(valid.length){editions=valid;current=valid.some(e=>e.id===saved.current)?saved.current:valid[0].id;}
    }
  } catch {}
  const card=()=>editions.find(e=>e.id===current);
  function remember(){try{
    const records=editions.map(d=>({...d,art:d.art===rawSeed.art?"@default":d.art,printArt:d.printArt===rawSeed.printArt?"@default":d.printArt}));
    localStorage.setItem(key,JSON.stringify({editions:records,current}));
  }catch{$("status").textContent="This browser cannot keep this draft. Save the print or disk files before closing.";}}
  function qr(url) {
    const code=new window.JCQR(-1,0); // M error correction in this encoder
    code.addData(allowedUrl(url)); code.make();
    const n=code.getModuleCount(), size=n+8, path=[];
    for(let y=0;y<n;y++)for(let x=0;x<n;x++)if(code.isDark(y,x))path.push("M"+(x+4)+" "+(y+4)+"h1v1h-1z");
    return '<svg class="qr" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Scan to open the gift" viewBox="0 0 '+size+" "+size+'" shape-rendering="crispEdges"><rect width="'+size+'" height="'+size+'" fill="white"/><path d="'+path.join("")+'" fill="#111"/></svg>';
  }
  function typeTitle(text){return text.length>15?' class="long"':"";}
  function header(d){return '<div class="card-head"><span>JC POSTCARDS</span><span>'+html(d.issue)+'</span></div>';}
  function picture(d,printing){return html(printing?d.printArt:d.art);}
  function renderFront(d,printing=false){
    const dedication=(d.greeting.startsWith("Frohe Weihnachten")?"FÜR ":"")+d.person.toUpperCase();
    return '<article class="art-card">'+header(d)+'<img alt="" class="front-picture" src="'+picture(d,printing)+'"><div class="front-foot"><strong'+typeTitle(d.title)+'>'+html(d.title)+'</strong><small>'+html(dedication)+'</small></div></article>';
  }
  function renderBack(d){
    const short=d.url.replace(/^https:\/\//,"");
    return '<article class="art-card">'+header(d)+'<div class="back-body"><div class="note"><h3'+(d.greeting.length>32?' class="long"':'')+'>'+html(d.greeting)+'</h3><p'+(d.note.length>153?' class="long"':'')+'>'+html(d.note)+'</p><p class="signed">'+html(d.sender)+'</p></div><div class="play"><a href="'+html(d.url)+'" aria-label="Open the gift">'+qr(d.url)+'</a><b>'+html(d.credit)+'</b><span class="work">'+html(d.work)+'</span><span class="fallback">'+(short.length<=45?html(short):"Scan the code or tap the square.")+'</span></div></div></article>';
  }
  function sheetHead(title,meta,note){return '<div class="sheet-head"><b>JC POSTCARDS</b><small>'+html(meta)+'</small></div><div class="sheet-note"><b>'+html(title)+'</b> · '+html(note)+'</div>';}
  function buildPrint(d) {
    $("print-card-sheet").innerHTML=sheetHead("Fold-over postcard","A4  /  100%  /  ONE SIDE","Cut the outer rectangle. Fold blank sides together at the two centre ticks.")+'<div class="fold-card">'+corners+'<div class="panel">'+renderFront(d,true)+'</div><div class="panel reverse">'+renderBack(d)+'</div><i class="foldmark left"></i><i class="foldmark right"></i></div><div class="ruler">50 mm</div><div class="sheet-legend">Finished size 148 × 105 mm. Print on your natural recycled card. If the stock is stiff, score the fold first. Enclose the object with the postcard.</div>';
    const selected=$("format").value, shapes=defs.filter(x=>selected==="all"||x.id===selected);
    $("print-label-sheet").innerHTML=sheetHead("Cut labels","A4  /  100%  /  ONE SIDE","Use your printer-compatible sticker sheet. Measure the 50 mm line before cutting.")+shapes.map(shape=>{
      const x=selected==="all"?shape.x:15,y=selected==="all"?shape.y:48;
      return '<div class="label-slot" data-kind="'+shape.id+'" style="left:'+x+"mm;top:"+y+"mm;width:"+shape.w+"mm;height:"+shape.h+'mm">'+corners+'<span class="dimension">'+html(shape.label)+" · "+shape.w+" × "+shape.h+' mm</span><div class="label-inner"><div class="label-copy"><small>JC POSTCARDS</small><img alt="" src="'+picture(d,true)+'"><b>'+html(d.title)+'</b><em>'+html(d.person)+'</em></div><a href="'+html(d.url)+'" aria-label="Open the gift">'+qr(d.url)+'</a></div></div>';
    }).join("")+'<div class="ruler">50 mm</div><div class="sheet-legend">Check each cutout against the object. Floppy: label recess, clear of shutter and holes. CD and record: label the sleeve. USB or found object: label a tag or sleeve. Keep connectors and playing surfaces clear.</div>';
  }
  function redraw(){
    const d=card(); $("screen-card").innerHTML=front?renderFront(d):renderBack(d);
    $("show-front").setAttribute("aria-pressed",String(front));$("show-back").setAttribute("aria-pressed",String(!front));
    $("screen-title").textContent=d.title;$("screen-issue").textContent=d.issue;
    $("review-heading").textContent=d.person==="You"?"Your next postcard":"For "+d.person;
    $("review-summary").textContent=d.credit+" · "+d.work;
    $("test-link").href=d.url;$("dispatch").hidden=d.decision!=="Yes";
    $("yes").setAttribute("aria-pressed",String(d.decision==="Yes"));$("no").setAttribute("aria-pressed",String(d.decision==="No"));
    const sel=$("editions"); sel.replaceChildren(...editions.map(e=>new Option(e.person+" · "+e.title,e.id,false,e.id===current)));
    buildPrint(d);
  }
  function showEdit(fresh=false){
    $("editor").hidden=false;$("editor").dataset.new=fresh?"yes":"no";
    const d=fresh?{...rawSeed,person:"",title:"",greeting:"",note:""}:card();
    for(const f of textFields)$("editor").elements[f].value=d[f];
    $("editor").elements.paperTone.value=d.paperTone||defaultPaper;
    $("editor").elements.image.value="";$("editor").elements.person.focus();
    $("status").textContent=fresh?"New postcard. Existing editions are kept.":"Change any field, then show the revised proof.";
  }
  async function resizeImage(src,width,quality){
    const img=new Image();img.src=src;await img.decode();const scale=Math.min(1,width/Math.max(img.naturalWidth,img.naturalHeight));
    const c=document.createElement("canvas");c.width=Math.max(1,Math.round(img.naturalWidth*scale));c.height=Math.max(1,Math.round(img.naturalHeight*scale));const ctx=c.getContext("2d");
    ctx.fillStyle="#fff";ctx.fillRect(0,0,c.width,c.height);ctx.drawImage(img,0,0,c.width,c.height);return c.toDataURL("image/jpeg",quality);
  }
  async function uploadedImage(file){
    const src=URL.createObjectURL(file);
    try{return await resizeImage(src,1450,.85);}finally{URL.revokeObjectURL(src);}
  }
  async function onPaper(art,tone){
    const img=new Image();img.src=art;await img.decode();
    const canvas=document.createElement("canvas");
    canvas.width=img.naturalWidth;canvas.height=img.naturalHeight;
    const ctx=canvas.getContext("2d");
    ctx.drawImage(img,0,0);
    const image=ctx.getImageData(0,0,canvas.width,canvas.height);
    // Approximate the paper white point. The unprinted stock supplies the highlights.
    const gains=[1,3,5].map(i=>255/Math.max(1,parseInt(tone.slice(i,i+2),16)));
    for(let i=0;i<image.data.length;i+=4){
      for(let channel=0;channel<3;channel++)image.data[i+channel]*=gains[channel];
    }
    ctx.putImageData(image,0,0);
    return canvas.toDataURL("image/jpeg",.85);
  }
  async function saveEdit(event){event.preventDefault();const f=event.currentTarget, isNew=f.dataset.new==="yes", d={...(isNew?rawSeed:card())};
    try{for(const k of textFields)d[k]=f.elements[k].value.trim();d.url=allowedUrl(d.url);
      const replacement=f.elements.image.files[0];
      const tone=f.elements.paperTone.value;
      if(replacement)d.art=await uploadedImage(replacement);
      if(replacement||tone!==(d.paperTone||defaultPaper)){
        d.printArt=d.art===rawSeed.art&&tone===defaultPaper?rawSeed.printArt:await onPaper(d.art,tone);
      }
      d.paperTone=tone;
      if(!acceptable(d))throw Error("Fill in each field and check the link and artwork.");
      if(isNew){d.id=typeof crypto.randomUUID==="function"?crypto.randomUUID():"card-"+Date.now();editions.push(d);current=d.id;}
      else{editions[editions.findIndex(x=>x.id===current)]=d;}
      d.decision="";f.hidden=true;front=true;$("status").textContent="Revised proof ready.";redraw();remember();
    }catch(err){$("status").textContent=err.message||"This image could not be opened. Try a JPEG or PNG.";}
  }
  function download(name,blob){const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);}
  async function mediaFiles(d){
    let art="";try{art=await resizeImage(d.art,600,.73);}catch{}
    return window.JCDisk.mediaFiles(d,art);
  }
  async function saveMedia(image){
    try{const files=await mediaFiles(card());if(image)download("JCPOST.IMG",new Blob([window.JCDisk.makeImage(files)],{type:"application/octet-stream"}));
      else download("START.HTM",new Blob([files[0].bytes],{type:"text/html;charset=utf-8"}));
    }catch(err){$("status").textContent=err.message;}
  }
  async function printSheet(mode){document.body.dataset.print=mode;buildPrint(card());
    await Promise.all(Array.from(document.querySelectorAll("#print-"+(mode==="card"?"card":"label")+"-sheet img")).map(i=>i.decode().catch(()=>{})));
    window.print();
  }
  $("show-front").onclick=()=>{front=true;redraw()};$("show-back").onclick=()=>{front=false;redraw()};
  $("yes").onclick=()=>{card().decision="Yes";$("editor").hidden=true;$("status").textContent="Proof approved. Print or save the files below.";redraw();remember();};
  $("no").onclick=()=>{card().decision="No";$("editor").hidden=true;$("status").textContent="Parked. Reopen this edition whenever you like.";redraw();remember();};
  $("edit").onclick=()=>showEdit();$("new-card").onclick=()=>showEdit(true);
  $("editions").onchange=e=>{current=e.target.value;front=true;$("editor").hidden=true;$("status").textContent="";redraw();remember();};
  $("editor").onsubmit=saveEdit;$("format").onchange=()=>buildPrint(card());
  $("print-card").onclick=()=>printSheet("card");$("print-labels").onclick=()=>printSheet("labels");
  $("file-htm").onclick=()=>saveMedia(false);$("file-img").onclick=()=>saveMedia(true);
  redraw();
})();
