"""Convert actual curses PTY recordings to PNG stills and GIF review clips."""
import argparse
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unicodedata

ANSI=re.compile(r'\x1b\[([0-?]*)([@-~])')
BASE16=['#000000','#cc5555','#4eaf67','#c7ad56','#607fcb','#b76bce','#4baab0','#dedede',
        '#666666','#ff6b6b','#65d785','#f0d264','#81a9ff','#dc82ef','#65d7dd','#ffffff']
DEFAULT_FG='#e9e5ef'


def color256(number):
    if number<16:return BASE16[number]
    if number<232:
        number-=16;levels=[0,95,135,175,215,255]
        return '#%02x%02x%02x'%(levels[number//36],levels[(number//6)%6],levels[number%6])
    gray=8+(number-232)*10
    return '#%02x%02x%02x'%(gray,gray,gray)


def cell_width(char):
    if unicodedata.combining(char):return 0
    return 2 if unicodedata.east_asian_width(char) in ('W','F') else 1


class AnsiTerminal:
    """Small VT parser for cursor-addressed ANSI emitted by curses in a PTY."""
    def __init__(self,columns,rows):
        self.columns,self.rows=columns,rows
        self.default=(DEFAULT_FG,False,False)
        self.cells=[[(' ',self.default) for _ in range(columns)] for _ in range(rows)]
        self.row=self.column=0
        self.style=list(self.default)
        self.pending=''

    def clear(self):
        self.cells=[[(' ',self.default) for _ in range(self.columns)] for _ in range(self.rows)]

    def has_content(self):
        return any(char.strip() for row in self.cells for char, _ in row)

    def write(self,char):
        if char=='\r':self.column=0;return
        if char=='\n':self.row=min(self.rows-1,self.row+1);return
        if char=='\b':self.column=max(0,self.column-1);return
        if char=='\t':self.column=min(self.columns-1,(self.column//8+1)*8);return
        if not char.isprintable():return
        width=cell_width(char)
        if width==0 and self.column:
            prior,style=self.cells[self.row][self.column-1]
            self.cells[self.row][self.column-1]=(prior+char,style)
            return
        if self.column+width>self.columns:
            self.row=min(self.rows-1,self.row+1);self.column=0
        if self.row<0 or self.row>=self.rows or self.column>=self.columns:return
        style=tuple(self.style)
        self.cells[self.row][self.column]=(char,style)
        for extra in range(1,width):
            if self.column+extra<self.columns:self.cells[self.row][self.column+extra]=('',style)
        self.column+=width

    def set_sgr(self,value):
        codes=[int(piece) if piece else 0 for piece in value.split(';')] or [0]
        index=0
        while index<len(codes):
            code=codes[index]
            if code==0:self.style=list(self.default)
            elif code==1:self.style[1]=True
            elif code==2:self.style[2]=True
            elif code in (21,22):self.style[1]=self.style[2]=False
            elif 30<=code<=37:self.style[0]=BASE16[code-30]
            elif 90<=code<=97:self.style[0]=BASE16[code-90+8]
            elif code==39:self.style[0]=DEFAULT_FG
            elif code==38 and index+2<len(codes) and codes[index+1]==5:
                self.style[0]=color256(codes[index+2]);index+=2
            elif code==38 and index+4<len(codes) and codes[index+1]==2:
                self.style[0]='#%02x%02x%02x'%tuple(codes[index+2:index+5]);index+=4
            index+=1

    def csi(self,parameters,final):
        private=parameters.startswith('?')
        values=parameters.lstrip('?').split(';') if parameters.lstrip('?') else []
        nums=[int(item) if item.isdigit() else 0 for item in values]
        first=nums[0] if nums else 0
        if final=='m':self.set_sgr(parameters)
        elif final in ('H','f'):
            self.row=max(0,min(self.rows-1,(nums[0] if nums and nums[0] else 1)-1))
            self.column=max(0,min(self.columns-1,(nums[1] if len(nums)>1 and nums[1] else 1)-1))
        elif final=='A':self.row=max(0,self.row-max(1,first))
        elif final=='B':self.row=min(self.rows-1,self.row+max(1,first))
        elif final=='C':self.column=min(self.columns-1,self.column+max(1,first))
        elif final=='D':self.column=max(0,self.column-max(1,first))
        elif final=='d':self.row=max(0,min(self.rows-1,max(1,first)-1))
        elif final=='G':self.column=max(0,min(self.columns-1,max(1,first)-1))
        elif final=='J' and first in (0,2):
            if first==2:self.clear()
            else:
                for row in range(self.row,self.rows):
                    start=self.column if row==self.row else 0
                    for col in range(start,self.columns):self.cells[row][col]=(' ',self.default)
        elif final=='K':
            start=0 if first==1 else self.column
            end=self.columns if first in (0,2) else min(self.columns,self.column+1)
            if first==2:start=0
            for col in range(start,end):self.cells[self.row][col]=(' ',self.default)
        elif final=='X':
            for col in range(self.column,min(self.columns,self.column+max(1,first))):self.cells[self.row][col]=(' ',self.default)
        elif final=='P':
            count=max(1,first);line=self.cells[self.row]
            del line[self.column:min(self.columns,self.column+count)]
            line.extend([(' ',self.default)]*count);del line[self.columns:]
        elif final=='@':
            count=max(1,first);line=self.cells[self.row]
            line[self.column:self.column]=[(' ',self.default)]*count;del line[self.columns:]
        elif final=='r' or private or final in ('h','l','t','q','s','u'):
            pass

    def feed(self,text):
        text=self.pending+text;self.pending='';index=0
        while index<len(text):
            char=text[index]
            if char=='\x1b':
                if index+1>=len(text):self.pending=text[index:];break
                if text[index+1]=='[':
                    match=ANSI.match(text,index)
                    if not match:self.pending=text[index:];break
                    self.csi(match.group(1),match.group(2));index=match.end();continue
                if text[index+1]=='(':
                    if index+2>=len(text):self.pending=text[index:];break
                    index+=3;continue
                if text[index+1]==']':
                    end=text.find('\x07',index+2)
                    if end<0:self.pending=text[index:];break
                    index=end+1;continue
                index+=2;continue
            self.write(char);index+=1

    def svg(self):
        width,height=self.columns*12,self.rows*22
        parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
               '<rect width="100%" height="100%" fill="#101016"/>']
        for row_number,row in enumerate(self.cells):
            runs=[];start=0;style=None;chars=[]
            for column,(char,current) in enumerate(row+[(' ',None)]):
                if current!=style and chars:
                    runs.append((start,style,''.join(chars)));chars=[];start=column
                if current!=style:style=current
                if char:chars.append(char)
            if runs:
                parts.append(f'<text xml:space="preserve" y="{row_number*22+18}" font-family="DejaVu Sans Mono,monospace" font-size="15">')
                for column,current,text in runs:
                    if current is None or not text.strip():continue
                    color,bold,dim=current
                    parts.append(f'<tspan x="{column*12+8}" fill="{color}" font-weight="{700 if bold else 400}" opacity="{0.58 if dim else 1}">{html.escape(text)}</tspan>')
                parts.append('</text>')
        parts.append('</svg>')
        return ''.join(parts)


def read_cast(path):
    lines=Path(path).read_text(encoding='utf-8').splitlines()
    header=json.loads(lines[0]);events=[json.loads(line) for line in lines[1:]]
    return header,events


def build_frames(cast_path,directory,fps=7):
    header,events=read_cast(cast_path)
    terminal=AnsiTerminal(header['width'],header['height'])
    outputs=[event for event in events if event[1]=='o']
    if not outputs:raise RuntimeError(f'No terminal output in {cast_path}')
    duration=outputs[-1][0];interval=1/fps;target=0.;frame=0
    Path(directory).mkdir(parents=True,exist_ok=True)
    for event in outputs:
        terminal.feed(event[2])
        while target<=event[0] and target<=duration:
            if terminal.has_content():
                svg=terminal.svg();svg_file=Path(directory)/f'frame-{frame:04}.svg'
                png_file=Path(directory)/f'frame-{frame:04}.png'
                svg_file.write_text(svg,encoding='utf-8')
                subprocess.run(['rsvg-convert','-o',str(png_file),str(svg_file)],check=True,capture_output=True)
                svg_file.unlink(missing_ok=True)
                frame+=1
            target+=interval
    # Preserve the last fully rendered screen even when the session ended between
    # regular GIF frame intervals (especially the disconnected-state capture).
    if terminal.has_content():
        svg_file=Path(directory)/f'frame-{frame:04}.svg'
        png_file=Path(directory)/f'frame-{frame:04}.png'
        svg_file.write_text(terminal.svg(),encoding='utf-8')
        subprocess.run(['rsvg-convert','-o',str(png_file),str(svg_file)],check=True,capture_output=True)
        svg_file.unlink(missing_ok=True);frame+=1
    if frame==0:
        raise RuntimeError(f'No visible terminal content in {cast_path}')
    return header,frame,duration,terminal


def png_from_cast(cast_path,destination):
    with tempfile.TemporaryDirectory(prefix='tvpn-frame-') as directory:
        _,_,_,terminal=build_frames(cast_path,directory,fps=1)
        files=sorted(Path(directory).glob('*.png'))
        shutil.copy2(files[-1],destination)


def gif_from_cast(cast_path,destination):
    with tempfile.TemporaryDirectory(prefix='tvpn-gif-') as directory:
        _,frames,_,_=build_frames(cast_path,directory)
        if frames<2:raise RuntimeError('Not enough screen frames for a GIF')
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-framerate','7',
                        '-i',str(Path(directory)/'frame-%04d.png'),'-filter_complex',
                        '[0:v]scale=1280:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer',
                        '-loop','0',str(destination)],check=True,capture_output=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input-dir',type=Path,default=Path(__file__).parent/'artifacts'/'terminal')
    parser.add_argument('--output-dir',type=Path,default=Path(__file__).parent/'artifacts'/'visuals')
    args=parser.parse_args()
    if not shutil.which('rsvg-convert') or not shutil.which('ffmpeg'):
        raise SystemExit('Requires rsvg-convert and ffmpeg; captures are taken from actual curses PTY sessions.')
    args.output_dir.mkdir(parents=True,exist_ok=True)
    for size in ('80x24','120x40','160x50'):
        png_from_cast(args.input_dir/f'main-{size}.cast',args.output_dir/f'main-{size}.png')
    png_from_cast(args.input_dir/'disconnected.cast',args.output_dir/'disconnected.png')
    for source,destination in [('connection-demo.cast','connection-demo.gif'),
                               ('globe-rotation.cast','globe-rotation.gif'),
                               ('region-transition.cast','region-transition.gif')]:
        gif_from_cast(args.input_dir/source,args.output_dir/destination)
    print(f'Exported PTY captures to {args.output_dir}')


if __name__=='__main__':main()
