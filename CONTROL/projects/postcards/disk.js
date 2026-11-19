/* Standard 3.5-inch high-density FAT12 disk image. No device access. */
(function () {
  "use strict";
  function makeImage(files, date = new Date()) {
    const sector = 512, total = 2880, fatSectors = 9, firstData = 33;
    const image = new Uint8Array(sector * total), view = new DataView(image.buffer);
    const ascii = (offset, text) => Array.from(text).forEach((ch,i) => { image[offset+i] = ch.charCodeAt(0); });
    const word = (offset,value) => view.setUint16(offset,value,true);
    const dword = (offset,value) => view.setUint32(offset,value,true);
    image.set([0xEB,0x3C,0x90]); ascii(3,"JCPOST  ");
    word(11,sector); image[13]=1; word(14,1); image[16]=2; word(17,224);
    word(19,total); image[21]=0xF0; word(22,fatSectors); word(24,18); word(26,2);
    image[38]=0x29; dword(39,date.getTime()>>>0); ascii(43,"JCPOSTCARDS"); ascii(54,"FAT12   ");
    image.set([0xEB,0xFE],62); image[510]=0x55; image[511]=0xAA;
    const fat=image.subarray(sector,sector*(1+fatSectors)); fat.set([0xF0,0xFF,0xFF]);
    function setCluster(index,next) {
      const off=Math.floor(index*1.5);
      if(index%2){fat[off]=(fat[off]&15)|((next<<4)&255); fat[off+1]=next>>4;}
      else{fat[off]=next&255; fat[off+1]=(fat[off+1]&240)|(next>>8);}
    }
    const root=19*sector;
    ascii(root,"JCPOSTCARDS"); image[root+11]=8;
    const datestamp=((Math.max(1980,Math.min(2107,date.getFullYear()))-1980)<<9)|
      ((date.getMonth()+1)<<5)|date.getDate();
    const timestamp=(date.getHours()<<11)|(date.getMinutes()<<5)|(date.getSeconds()>>1);
    let cluster=2;
    if(files.length>223) throw Error("Too many files for this disk.");
    files.forEach((file,i) => {
      if(!/^[A-Z0-9_]{1,8}\.[A-Z0-9_]{1,3}$/.test(file.name)) throw Error("Use 8.3 DOS filenames.");
      const [name,extension]=file.name.split(".");
      const bytes=file.bytes; const needed=Math.ceil(bytes.length/sector);
      if(cluster+needed-2>total-firstData) throw Error("This content exceeds a 1.44 MB disk.");
      const entry=root+32*(i+1);
      ascii(entry,name.padEnd(8," ")+extension.padEnd(3," ")); image[entry+11]=0x20;
      word(entry+22,timestamp); word(entry+24,datestamp); word(entry+26,needed?cluster:0); dword(entry+28,bytes.length);
      for(let n=0;n<needed;n++,cluster++){
        setCluster(cluster,n+1===needed?0xFFF:cluster+1);
        image.set(bytes.subarray(n*sector,(n+1)*sector),(firstData+cluster-2)*sector);
      }
    });
    image.set(fat,(1+fatSectors)*sector);
    return image;
  }
  const html = x => String(x).replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  function mediaFiles(d,art){
    const play=html(d.url);
    const page='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html(d.title)+'</title><style>html{background:#f1ecdd;color:#173f35}body{margin:4vh auto;padding:20px;max-width:520px;font:20px/1.45 Georgia,serif}img{width:100%;display:block}small{font:12px/1.4 monospace;color:#93402e}h1{font-weight:normal;font-size:44px;line-height:1;margin:19px 0}p{white-space:pre-line}a{color:#153f34}footer{font:13px/1.5 sans-serif}</style><main><small>JC POSTCARDS · '+html(d.issue)+'</small><h1>'+html(d.title)+'</h1>'+(art?'<img alt="" src="'+art+'">':'')+'<h2>'+html(d.greeting)+'</h2><p>'+html(d.note)+'</p><i>'+html(d.sender)+'</i><hr><p><a href="'+play+'">'+html(d.work)+'</a><br>'+html(d.credit)+'</p><footer>The note opens offline. Connect to open the linked gift.</footer></main></html>';
    const note=[d.greeting,"",d.note,"",d.sender,"",d.credit+" — "+d.work,d.url,""].join("\r\n");
    const enc=new TextEncoder();return [{name:"START.HTM",bytes:enc.encode(page)},{name:"NOTE.TXT",bytes:enc.encode(note)}];
  }
  window.JCDisk={makeImage,mediaFiles};
})();
