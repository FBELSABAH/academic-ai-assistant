from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from document_reader import read_document
from assessments import extract, candidates


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def read(self,name,text):
        p=self.root/name;p.write_text(text);return read_document(p,extract)
    def test_html_scripts_are_not_course_content(self):
        r=self.read('page.html','<script>Exam October 10</script><p>Assignment 2 due October 11</p>')
        self.assertNotIn('October 10',r['pages'][0][1])
        self.assertIn('October 11',r['pages'][0][1])
    def test_csv_rows_keep_assessment_and_date_together(self):
        r=self.read('schedule.csv','Assessment,Due\nQuiz 2,"October 9, 2026"\n')
        self.assertEqual(candidates(r['pages'][0][1],2026,'Schedule')[0]['date'],'2026-10-09')
    def test_unsupported_file_explicit(self):
        r=self.read('old.doc','binary')
        self.assertEqual(r['pages'],[]);self.assertIn('Unsupported',r['notes'][0])
    def test_spreadsheet_preserves_row_and_flags_numeric_dates(self):
        p=self.root/'dates.xlsx'
        with zipfile.ZipFile(p,'w') as z:
            z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c t="inlineStr"><is><t>Quiz 1</t></is></c><c t="inlineStr"><is><t>October 12</t></is></c></row></sheetData></worksheet>')
        r=read_document(p,extract)
        self.assertIn('Quiz 1 | October 12',r['pages'][0][1]);self.assertTrue(r['notes'])
    def test_real_scanned_pdf_ocr(self):
        from PIL import Image,ImageDraw,ImageFont
        p=self.root/'scan.pdf'
        image=Image.new('RGB',(1600,500),'white');draw=ImageDraw.Draw(image)
        draw.text((80,100),'Assignment 2 due October 20, 2026',font=ImageFont.load_default(size=48),fill='black')
        image.save(p,'PDF',resolution=150)
        r=read_document(p,extract)
        self.assertEqual(r['ocr_pages'],[1])
        self.assertIn('October 20',r['pages'][0][1])
        self.assertTrue(any('require review' in s for s in r['notes']))
    def test_image_ocr_failure_is_reported(self):
        from PIL import Image
        p=self.root/'image.png';Image.new('RGB',(50,50),'white').save(p)
        with patch('document_reader.ocr',side_effect=TimeoutError):r=read_document(p,extract)
        self.assertIn('OCR failed',' '.join(r['notes']))

if __name__=='__main__':unittest.main()
