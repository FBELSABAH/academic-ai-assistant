import tempfile
import unittest
from pathlib import Path
from bs4 import BeautifulSoup
from src.announcements import parse_posts
from src.course_library import CourseLibrary
from tests.test_course_library import Session, Response, page, COURSE, ORIGIN

class AnnouncementTests(unittest.TestCase):
    def test_fetch_and_repeat(self):
        forum=ORIGIN+'/mod/forum/view.php?id=3';thread=ORIGIN+'/mod/forum/discuss.php?d=4'
        post='<article data-region="post" data-post-id="5"><h3>Assignment 2</h3><time datetime="2026-10-05T12:00:00Z"></time><div data-region="post-content">Assignment 2 extended to October 15.</div><a href="/mod/forum/post.php?reply=5">Reply</a></article>'
        routes={COURSE:Response(COURSE,page('<a href="'+forum+'">Announcements</a>')),forum:Response(forum,page('<a href="'+thread+'">Assignment 2</a>')),thread:Response(thread,page(post))}
        with tempfile.TemporaryDirectory() as tmp:
            session=Session(routes);lib=CourseLibrary(session,COURSE,Path(tmp));lib.sync()
            item=lib.manifest['pages'][thread+'#p5']
            self.assertEqual(item['source_type'],'announcement');self.assertTrue(item['verified_in_last_run'])
            self.assertEqual(item['posted_at'],'2026-10-05T12:00:00Z')
            self.assertFalse(any('post.php' in u for u,_ in session.calls))
            lib=CourseLibrary(session,COURSE,Path(tmp));lib.sync()
            self.assertEqual(len([p for p in lib.manifest['pages'].values() if p.get('source_type')=='announcement']),1)
    def test_unidentified_forum_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib=CourseLibrary(None,COURSE,Path(tmp))
            soup=BeautifulSoup('<main><a href="/mod/forum/view.php?id=4">Student discussion</a><a href="/mod/forum/discuss.php?d=3">Topic</a></main>','html.parser')
            self.assertEqual(list(lib.links(soup,COURSE)),[])
    def test_missing_post_identity_is_not_invented(self):
        self.assertEqual(parse_posts(BeautifulSoup('<div class="forumpost"><div class="posting">hello</div></div>','html.parser'),COURSE),[])

if __name__=='__main__':unittest.main()
