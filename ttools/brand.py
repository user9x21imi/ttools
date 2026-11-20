"""High-resolution Unicode wordmark. No fonts or graphics protocols at runtime."""
import base64
from functools import lru_cache
import zlib
WIDTH,HEIGHT=640,200
STENCIL=zlib.decompress(base64.b85decode(
    'c-rmSO_rk|5CC9!EL?H~kK&d32IjrKm`BMGvUK5t=|qvDD4_i5#mrRg?3OP^5Q`#8Nk~XYNJ!Apd+%rQe$VTC8qb@('
    'mw4idC!ToXiTCT?8pF?N?#6uM?JfVUH=riq7<!dUNW30(Gdu>~_#O@n&-nC2{W*SM&wl>Aw7nkXffkO-=#91U3O$cL'
    'cx~vAXTk&UXm|#lmmcq)tv*n|>rvuslXkl|aJ_Kitf=GN^IR{Sw<NbO+`!;zuD9Q34@b*>1A}L{UYE89#}o7{*Xz+r'
    '1T_p^&-Dg$Vr)2{^2W41@E7O}T+gTNf$yL<GQHTH+W-NtmNT9~?ScR4@Zfo-*P-^%pQ5L^o<;3Dw3I#S^{Bl?ujVV>'
    't8hFgx1sJ06>rAgV{CdOY7hMddDG|L4DYov`#77|%S4`AhiBc}21*y&kL!h)Fu*sji{pXeZT;tnW8kgNciq$Bx}fL4'
    '%Nuyx{L}X4*nanil4q)(3FBk{-ag+w5^s9}el@-DTzTNzqF2oiy71g??M?FBO~m&->2(*pM{K|Q=A36K?*VRXHvSl%'
    'ir2GyI``bo-ui-PdRu#ZoXjt-?e*a_?5S-aCi9=W*(-xJ&y~I6n1No*6Uv^hX3u4Bzg{)c-h9M+6+MNr&NY_I8xDJ5'
    'meKB@Hxv2Le6#27@dlswFw<KouTRtT%N~{AU-3GhcgPjbc)X6f=IQeu*}v3)x#acv6L-n$a&L%V{_yjQ*PR8AJ->h_'
    'gzr6To;l-{=4aR=Q^VuDKj6}Cs`M}S{RT@5_jxLvp$X5HJd_{6Vrk2R`HL;&FR)a0#Ovzb=MFYKM*aue)jV!~ddS21'
    '^OWb$uylFYd!F~W>koazW2}$#ljm{QZ+hnS2X}p`{Q=MA>tBV|zj{+z<C(iY*I*W_dSjgDqxZ_{2YO`;&-34?zVYpI'
    '&x2KG*<;pUKKFMr&H0pDAJVAI#qxOdtN4DSyyNw?x_7+(SIu9z^+~pe>!+HopJrv&l9$zYJz3u+J>^c<pS36QQ_|zr'
    '$F(Q&aph0f@9Fw!l4@o93sYr(L6bjV8lPwPKQ!^Uz3=@}-k))bI?lah6-{_!VgG2MJ=gMB`&*jo-k(zmuPf}oP04-~'
    '`Fk=$c?y3IPwfv{vcNISgg2mJ)x+<F_um-%p$2`fA@^4e>*sSj{%Y<?ThHCo&NiM$vQX7Ae-a=eAt530Pe$)=i0SX~'
    'BqSsxBqSsxV*CMLij!O'
))

def pixel(x,y):
    x=max(0,min(WIDTH-1,x));y=max(0,min(HEIGHT-1,y))
    return bool(STENCIL[y*(WIDTH//8)+x//8] & (128>>(x%8)))

@lru_cache(maxsize=32)
def logo(columns):
    columns=max(20,min(100,columns));height=max(7,round(columns*.19))
    dots=((0,0,1),(0,1,2),(0,2,4),(0,3,64),(1,0,8),(1,1,16),(1,2,32),(1,3,128))
    lines=[]
    for y in range(height):
        row=[]
        for x in range(columns):
            bits=0
            for dx,dy,bit in dots:
                sx=(2*x+dx+.5)*WIDTH/(2*columns)
                sy=(4*y+dy+.5)*HEIGHT/(4*height)
                # Area sampling preserves the thin underline and curved strokes.
                rx=WIDTH/(2*columns)*.24;ry=HEIGHT/(4*height)*.24
                if any(pixel(int(sx+ox),int(sy+oy)) for ox in (-rx,rx) for oy in (-ry,ry)):bits|=bit
            row.append(chr(0x2800+bits) if bits else ' ')
        lines.append(''.join(row))
    return tuple(lines)
