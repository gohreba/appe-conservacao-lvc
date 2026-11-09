"""Small dependency-free reader for the BIFF8 cell values of the supplied legacy .xls.

READ-ONLY. Supports numeric, formula-cached, shared-string, boolean cells.
It deliberately does not execute Excel formulas, read macros or follow external links.
For other files prefer converting to XLSX or providing the standardized CSV import.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import struct
from typing import Iterator

U16=lambda data,off=0:struct.unpack_from('<H',data,off)[0]
U32=lambda data,off=0:struct.unpack_from('<I',data,off)[0]

class XlsReadError(ValueError): pass

@dataclass
class Sheet:
    name: str
    cells: dict[tuple[int,int],object]
    def cell(self,row:int,col:int,default=None):
        """1-based row and column."""
        return self.cells.get((row,col),default)
    def nonempty_rows(self):
        rows={}
        for (r,c),val in self.cells.items():rows.setdefault(r,{})[c]=val
        for r in sorted(rows):yield r,rows[r]

class _Ole:
    def __init__(self,blob:bytes):
        if blob[:8]!=bytes.fromhex('d0cf11e0a1b11ae1'):raise XlsReadError('Not an OLE2 .xls file')
        self.blob=blob;self.sector_size=1<<U16(blob,30)
        self.cutoff=U32(blob,56)
        self.difat=[U32(blob,76+4*i) for i in range(109)]
        self.difat=[sid for sid in self.difat if sid<0xFFFFFFFA]
        sid=U32(blob,68); remaining=U32(blob,72); seen=set()
        while remaining and sid<0xFFFFFFFA and sid not in seen:
            seen.add(sid);z=self._sector(sid)
            self.difat.extend(x for x in struct.unpack_from('<'+str(self.sector_size//4-1)+'I',z,0) if x<0xFFFFFFFA)
            sid=U32(z,self.sector_size-4);remaining-=1
        self.fat=[]
        for sid in self.difat:
            self.fat.extend(struct.unpack_from('<'+str(self.sector_size//4)+'I',self._sector(sid)))
        d=self._chain(U32(blob,48));self.entries={}
        for o in range(0,len(d),128):
            ent=d[o:o+128]
            if len(ent)<128:break
            if U16(ent,64)<2:continue
            name=ent[:U16(ent,64)-2].decode('utf-16le',errors='replace')
            self.entries[name]=(ent[66],U32(ent,116),struct.unpack_from('<Q',ent,120)[0])
    def _sector(self,sid:int)->bytes:
        o=512+sid*self.sector_size
        return self.blob[o:o+self.sector_size]
    def _chain(self,sid:int)->bytes:
        out=bytearray();seen=set()
        while sid<0xFFFFFFFA:
            if sid in seen:raise XlsReadError('OLE FAT cycle')
            seen.add(sid);out.extend(self._sector(sid));sid=self.fat[sid]
        return bytes(out)
    def workbook(self)->bytes:
        for name in ('Workbook','Book'):
            if name in self.entries:
                typ,sid,size=self.entries[name]
                if size<self.cutoff:raise XlsReadError('Small Workbook stream is not supported')
                return self._chain(sid)[:size]
        raise XlsReadError('Workbook stream not found')

def records(data:bytes,start:int=0,end:int|None=None)->Iterator[tuple[int,int,bytes]]:
    end=len(data) if end is None else end
    p=start
    while p+4<=end:
        kind,n=struct.unpack_from('<HH',data,p)
        if p+4+n>end:raise XlsReadError('Invalid BIFF record size')
        yield p,kind,data[p+4:p+4+n]
        p+=4+n

def _rk(v:int)->float|int:
    if v&2:
        signed=struct.unpack('<i',struct.pack('<I',v))[0]
        x=signed>>2
    else:
        x=struct.unpack('<d',struct.pack('<Q', (v&0xFFFFFFFC)<<32))[0]
    return x/100 if v&1 else x

class _Chunks:
    def __init__(self,chunks:list[bytes]):self.chunks=chunks;self.i=0;self.pos=0
    def _advance(self):
        while self.i<len(self.chunks) and self.pos==len(self.chunks[self.i]):
            self.i+=1;self.pos=0
        if self.i>=len(self.chunks):raise XlsReadError('Truncated SST')
    def read(self,n):
        out=bytearray()
        while n:
            self._advance()
            b=self.chunks[self.i];k=min(n,len(b)-self.pos)
            out+=b[self.pos:self.pos+k];self.pos+=k;n-=k
        return bytes(out)
    def chars(self,count,wide):
        text=[]
        while count:
            old=self.i
            self._advance()
            if self.i!=old: # CONTINUE record opening a character segment has 1 compression byte
                wide=bool(self.read(1)[0]&1)
            b=self.chunks[self.i]
            chars=min(count,(len(b)-self.pos)//(2 if wide else 1))
            if chars==0:raise XlsReadError('Unexpected unicode split')
            raw=b[self.pos:self.pos+chars*(2 if wide else 1)]
            text.append(raw.decode('utf-16le' if wide else 'latin1',errors='replace'))
            self.pos+=len(raw);count-=chars
        return ''.join(text)

def _sst(chunks):
    stream=_Chunks(chunks)
    total,uniq=struct.unpack('<II',stream.read(8));strings=[]
    for _ in range(uniq):
        n=U16(stream.read(2));flags=stream.read(1)[0]
        runs=U16(stream.read(2)) if flags&8 else 0
        extsize=U32(stream.read(4)) if flags&4 else 0
        txt=stream.chars(n,bool(flags&1)) if n else ''
        if runs:stream.read(runs*4)
        if extsize:stream.read(extsize)
        strings.append(txt)
    return strings

def load_xls(path:str|Path)->dict[str,Sheet]:
    data=_Ole(Path(path).read_bytes()).workbook()
    rec=list(records(data));meta=[];strings=[]
    for i,(_,typ,d) in enumerate(rec):
        if typ==0x85:
            offset=U32(d);n=d[6];high=bool(d[7]&1)
            name=d[8:8+n*(2 if high else 1)].decode('utf-16le' if high else 'latin1',errors='replace')
            meta.append((name,offset))
        elif typ==0xFC:
            chunks=[d];j=i+1
            while j<len(rec) and rec[j][1]==0x3C:
                chunks.append(rec[j][2]);j+=1
            strings=_sst(chunks)
    out={}
    for i,(name,offset) in enumerate(meta):
        end=meta[i+1][1] if i+1<len(meta) else len(data)
        cells={};last_formula=None
        for _,typ,d in records(data,offset,end):
            if typ==0xFD:
                r,c,xf,idx=struct.unpack_from('<HHHI',d,0)
                if idx>=len(strings):raise XlsReadError(f'Invalid SST index {idx} ({name})')
                cells[r+1,c+1]=strings[idx]
            elif typ==0x203:
                r,c,xf,num=struct.unpack_from('<HHHd',d)
                cells[r+1,c+1]=num
            elif typ==0x27E:
                r,c,xf,v=struct.unpack_from('<HHHI',d)
                cells[r+1,c+1]=_rk(v)
            elif typ==0xBD:
                r,c0=struct.unpack_from('<HH',d)
                for i2 in range((len(d)-6)//6):
                    xf,v=struct.unpack_from('<HI',d,4+i2*6)
                    cells[r+1,c0+i2+1]=_rk(v)
            elif typ==0x6:
                r,c,xf=struct.unpack_from('<HHH',d)
                cached=d[6:14]
                if cached[6:]==b'\xff\xff':
                    code=cached[0];value=cached[2]
                    if code==0: last_formula=(r+1,c+1)
                    elif code==1:cells[r+1,c+1]=bool(value);last_formula=None
                    elif code==2:cells[r+1,c+1]=f'#EXCEL_ERR_{value}' ;last_formula=None
                    else:last_formula=None
                else: cells[r+1,c+1]=struct.unpack('<d',cached)[0];last_formula=None
            elif typ==0x207 and last_formula:
                n=U16(d);flags=d[2]
                cells[last_formula]=d[3:3+n*(2 if flags&1 else 1)].decode('utf-16le' if flags&1 else 'latin1','replace')
                last_formula=None
            elif typ==0x205:
                r,c,xf,value,iserr=struct.unpack_from('<HHHBB',d)
                cells[r+1,c+1]=f'#EXCEL_ERR_{value}' if iserr else bool(value)
            elif typ==0x204:
                r,c,xf,n=struct.unpack_from('<HHHH',d)
                flags=d[8];text=d[9:9+n*(2 if flags&1 else 1)].decode('utf-16le' if flags&1 else 'latin1','replace')
                cells[r+1,c+1]=text
        out[name]=Sheet(name,cells)
    return out
