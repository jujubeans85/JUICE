import {createBackup,checkBackup,backupFilename,digest,workState,MAX_BACKUP_BYTES} from './backup-core.mjs';
import {rehearseRestore,recoveryJournal,recoverPrevious} from './backup-storage.mjs';
const $=s=>document.querySelector(s),KEY='cj-atlas-backup-status-v1';
const when=value=>value?new Date(value).toLocaleString():'Never';
function readStatus(){try{return JSON.parse(localStorage.getItem(KEY)||'{}')}catch{return {}}}
export function recordBackupStatus(patch){const next={...readStatus(),...patch};try{localStorage.setItem(KEY,JSON.stringify(next))}catch{}return next;}
export function saveBackupFile(data){
  const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'})),a=document.createElement('a');
  a.href=url;a.download=backupFilename(data);document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
}
export class BackupPanel {
  constructor({snapshot,registry,restore,health=()=>true}) {
    Object.assign(this,{snapshot,registry,restore,health});this.available=false;this.checked=null;
    $('#backup-dialog').addEventListener('cancel',event=>{if(this.busy)event.preventDefault();});
    $('#backup-dialog').addEventListener('close',()=>this.trigger?.focus());
    $('#export').onclick=()=>this.open();$('#backup-save').onclick=()=>this.run(()=>this.save());
    $('#backup-file').onchange=e=>{const file=e.target.files[0];e.target.value='';this.checked=null;this.renderActions();if(file)this.run(()=>this.checkFile(file));};
    $('#backup-rehearse').onclick=()=>this.run(()=>this.rehearse());$('#backup-restore').onclick=()=>this.run(()=>this.restore(this.checked.data));
    $('#backup-recover').onclick=()=>this.run(async()=>{await recoverPrevious();location.reload();});
    $('#backup-persist').onclick=()=>this.run(async()=>{const ok=await navigator.storage?.persist?.();this.message(ok?'Browser eviction protection granted. This is still not a backup.':'Eviction protection was not granted. Keep a downloaded backup.');await this.refresh();});
    this.renderActions();
  }
  message(text){$('#backup-message').textContent=text;}
  changed(){if(!this.available)return;const text='Work may have changed. Open Backups to check your saved copy.';$('#backup-summary').textContent=text;$('#backup-current').textContent=text;}
  renderActions(){for(const id of ['backup-save','backup-file'])$('#'+id).disabled=!this.available||this.busy;for(const id of ['backup-rehearse','backup-restore'])$('#'+id).disabled=!this.checked||!this.available||this.busy;$('#backup-persist').disabled=this.busy||!navigator.storage?.persist;$('#backup-dialog [data-close]').disabled=Boolean(this.busy);$('#backup-recover').disabled=Boolean(this.busy);}
  async run(fn){if(this.busy)return;this.busy=true;this.renderActions();try{await fn()}catch(e){this.message(e.message);try{$('#backup-recover').hidden=!await recoveryJournal()}catch{}}finally{this.busy=false;this.renderActions();}}
  async open(){this.trigger=document.activeElement;const dialog=$('#backup-dialog');if(!dialog.open)dialog.showModal();await this.run(()=>this.refresh());}
  async refresh(){
    const s=readStatus();let persistent=false;try{persistent=await navigator.storage?.persisted?.()}catch{}
    $('#backup-browser').textContent=!this.health()?'Some work may be session-only: a browser store reported a failure. Export before leaving.':persistent?'Eviction protection granted · still browser storage':'Best-effort browser storage · can be cleared or evicted';
    $('#backup-download').textContent=s.download?when(s.download)+' · download requested; saving unconfirmed':'No download requested on this browser';
    $('#backup-checked').textContent=s.checked?when(s.checked)+' · selected file validated':'No saved file checked on this browser';
    $('#backup-drill').textContent=s.rehearsed?when(s.rehearsed)+' · isolated storage write/read passed':'No isolated storage rehearsal yet';
    $('#backup-restored').textContent=s.restored?when(s.restored)+' · merged data read back on this browser':'No live restore verified on this browser';
    $('#backup-recover').hidden=!await recoveryJournal();
    let current='Open the Atlas fully before making a backup.';
    if(this.available){if(!crypto.subtle)current='Integrity checks require HTTPS. This preview cannot verify backups.';else{const hash=await digest(workState(this.snapshot()));current=s.checkedHash===hash?'Current work matches the last checked file.':'Current work has no matching checked file. Save a new backup after this session.';}}
    $('#backup-current').textContent=current;$('#backup-summary').textContent=current;
  }
  async save(){
    this.message('Preparing the existing v3 export…');
    const data=await createBackup(this.snapshot(),this.registry());saveBackupFile(data);
    recordBackupStatus({download:new Date().toISOString()});this.message('Download requested. Find it in Files or Finder, then choose that saved file below to check it.');await this.refresh();
  }
  async checkFile(file){
    this.checked=null;this.renderActions();
    if(file.size>MAX_BACKUP_BYTES)throw Error('Use a backup smaller than 60 MB.');
    const checked=await checkBackup(JSON.parse(await file.text()),this.registry());this.checked=checked;
    const c=checked.counts;recordBackupStatus({checked:new Date().toISOString(),checkedHash:await digest(workState(checked.data))});
    this.message(`${checked.integrity}. ${c.crates} crates · ${c.ordered_entries} ordered entries · ${c.recordings} recordings · ${c.research_jobs} research jobs · ${c.concept_choices} choices. Nothing has been restored.`);await this.refresh();
  }
  async rehearse(){
    this.message('Rehearsing restoration in separate temporary browser databases…');
    await rehearseRestore(this.checked.data);recordBackupStatus({rehearsed:new Date().toISOString()});
    this.message('Isolated storage rehearsal passed: restored sections read back identically and temporary databases removed. This does not verify another device, future availability or the full interface.');await this.refresh();
  }
}
