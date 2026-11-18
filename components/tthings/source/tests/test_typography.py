import unittest
from tthings.typography import number_art,STYLES,big_text
from tthings.effects import Frame
from tthings.system_fetch import parse_logo,Logo3D,info_rows

class TypographyTests(unittest.TestCase):
    def test_styles_resize_and_clipped_drawing(self):
        for style in STYLES:
            for width,height in [(1,1),(20,3),(60,10),(120,20)]:
                art=number_art('72.5%',width,height,style,1)
                self.assertLessEqual(art.w,width);self.assertLessEqual(art.h,height)
                self.assertTrue(any(c!=' ' for row in art.cells for c,_ in row))
                frame=Frame(width,height);big_text(frame,-2,-2,'72.5%','#ffffff',width=width,height=height,style=style)
                self.assertTrue(all(len(row)==width for row in frame.cells))
    def test_styles_visibly_differ_and_size_changes(self):
        arts=[number_art('17',80,12,style).plain() for style in STYLES]
        self.assertEqual(len(set(arts)),len(STYLES))
        self.assertGreater(number_art('17',80,12,size=1).w,number_art('17',80,12,size=-1).w)

class LogoTests(unittest.TestCase):
    def test_color_placeholders_and_real_geometry_rotation(self):
        logo=parse_logo({'lines':'$1XX  $2XX\n XX XX\n  XXX','colors':['34','37']})
        cells,width,height=logo
        self.assertEqual(width,6);self.assertEqual(height,3)
        self.assertEqual(cells[0][3],'#82aee8');self.assertEqual(cells[2][3],'#dbe5ee')
        renderer=Logo3D(logo)
        self.assertNotEqual(renderer.render(50,20,0).plain(),renderer.render(50,20,2).plain())
        self.assertGreater(len(renderer.points),len(cells)*4)
    def test_only_display_fields_from_fastfetch(self):
        name,rows=info_rows([{'type':'OS','result':{'prettyName':'Test OS'}},{'type':'Host','result':{'vendor':'Maker','name':'Model','serial':'PRIVATE','uuid':'PRIVATE'}},{'type':'Battery','result':[{'capacity':77,'status':['Connected','Charging']}]}])
        self.assertEqual(name,'Test OS');self.assertNotIn('PRIVATE',str(rows));self.assertIn('Connected / Charging',str(rows))

if __name__=='__main__':unittest.main()
