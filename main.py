import asyncio
import collections
import enum
import http.client
import itertools
import math
import os
import re
import shutil

import requests
import urllib.parse

import bs4
from PIL import Image

SIZE = collections.namedtuple('SIZE', ('WIDTH', 'HEIGHT'))


class SIZE(SIZE):
    def __new__(cls, width, height):
        assert isinstance(width, (type(None), int))
        assert isinstance(height, (type(None), int))

        return super().__new__(cls, width, height)


class HtmlType(enum.Enum):
    CATEGORY = 1
    POST = 2


class Crawler:
    __image_size = SIZE(600, 600)
    __error_code = 0
    __image_uri_regex = r'(http:[^\'\\,\s)]+)'
    __image_uri_regex = re.compile(__image_uri_regex)
    __image_size_regex = r'([\ ]+[0-9]+)'
    __image_size_regex = re.compile(__image_size_regex)

    __default_headers = requests.utils.default_headers()
    __default_headers.update(
        {'User-Agent': 'My User Agent 1.0'}
    )

    def __init__(self, url, save_path, size=None):
        assert isinstance(url, str)
        assert isinstance(save_path, str)
        assert isinstance(size, (type(None), SIZE))

        if not os.path.exists(save_path):
            raise FileNotFoundError()

        self.__save_path = save_path

        if size is not None:
            self.__image_size = size

        html_type = self.__get_html_type(url)

        if html_type == HtmlType.CATEGORY:
            asyncio.run(self.__crawl_category(url, True))
        else:
            assert html_type == HtmlType.POST

            asyncio.run(self.__crawl_post(url))

    async def __crawl_post(self, url):
        print(f'{url} requests...', end='')

        response = requests.get(url, headers=self.__default_headers)
        if response.status_code != 200:
            raise ValueError

        soup = bs4.BeautifulSoup(response.text, features='html.parser')
        title_soup = soup.find('title')
        if title_soup is None:
            raise RuntimeError

        texts = title_soup.text.split(':')
        blog_title = texts[0].strip()
        post_view_soups = soup.find_all('div', {'class': 'post_view'})
        for post_view_soup in post_view_soups:
            div_soup = post_view_soup.find('div', {'class': 'post_title'})
            if div_soup is None:
                title_area_soup = post_view_soup.find('div', {'class': 'post_title_area'})
                if title_area_soup is None:
                    print(f'failed through getting title: {url}')
                    continue

                post_title = title_area_soup.contents[1].string
            else:
                a_soup = div_soup.find('a')
                post_title = a_soup.text

            category_soup = post_view_soup.find('span', {'class': 'post_title_category'})
            if category_soup is None:
                raise RuntimeError

            category = category_soup.text
            print(f'\t{category}/{post_title} requests...')

            children = post_view_soup.find_all('img', {'class': 'image_mid'})
            if children:
                folder_path = self.__get_file_path(save_path, blog_title, category, post_title)
                if not os.path.exists(folder_path):
                    os.makedirs(folder_path)

                if len(os.listdir(folder_path)) == len(children):
                    print('\t\talready exists')
                    continue
                else:
                    shutil.rmtree(folder_path)
                    os.mkdir(folder_path)

                if children:
                    await self.__save_images(folder_path, children)

            await asyncio.sleep(2)

        await asyncio.sleep(2)

    async def __crawl_category(self, url, is_parsing_pages):
        base_url = self.__get_base_url(url)
        response = requests.get(url, headers=self.__default_headers)
        if response.status_code != 200:
            raise ValueError

        soup = bs4.BeautifulSoup(response.text, features='html.parser')
        div_soup = soup.find('div', {'id': 'titlelist_list'})
        if div_soup is None:
            raise RuntimeError

        for li_soup in div_soup.find_all('li'):
            a_soup = li_soup.find('a')
            local_url = a_soup.attrs['href']
            post_url = urllib.parse.urljoin(base_url, local_url)
            await self.__crawl_post(post_url)

        if is_parsing_pages:
            div_soup = soup.find('div', {'id': 'titlelist_paging'})
            span_soup = div_soup.find('span', {'class': 'page'})
            for a_soup in span_soup.find_all('a'):
                local_url = a_soup.attrs['href']
                page_url = urllib.parse.urljoin(base_url, local_url)
                await self.__crawl_category(page_url, False)

            span_soup = div_soup.find('a', {'class': 'next'})
            if span_soup is not None:
                a_soup = span_soup.find('a')
                local_url = a_soup.attrs['href']
                page_url = urllib.parse.urljoin(base_url, local_url)
                await self.__crawl_category(page_url, True)

    def image_size(self, size) -> None:
        assert isinstance(size, SIZE)

        self.__image_size = size

    image_size = property(None, image_size)

    @property
    def error_code(self) -> int:
        return self.__error_code

    async def __save_images(self, save_path, children):
        iterator = itertools.dropwhile(self.__filter_image, children)
        zerofill = math.ceil(math.log10(len(children)))

        for i, child in enumerate(iterator, 1):
            uri = self.__extract_image_uri(child)
            file_name = os.path.split(uri)[-1]
            ext = os.path.splitext(file_name)[-1]
            file_name = f'{i:0{zerofill}d}{ext}'
            file_path = os.path.join(save_path, file_name)

            while True:
                try:
                    urllib.request.urlretrieve(uri, file_path)
                    break
                except http.client.RemoteDisconnected:
                    await asyncio.sleep(10)
                    print('remote disconnected. wait 10 sec. after that try again')

            print('\033[3;0H', end='')
            print(f'{i:0{zerofill}d}/{len(children)}')

    def __filter_image(self, tag) -> bool:
        assert isinstance(tag, bs4.element.Tag)

        text = tag.attrs['onclick']
        r = re.findall(self.__image_size_regex, text)
        w, h = map(int, r)

        return self.__image_size.WIDTH > w or self.__image_size.HEIGHT > h

    @classmethod
    def __extract_image_uri(cls, tag) -> str:
        text = tag.attrs['onclick']

        return re.search(cls.__image_uri_regex, text).group()

    @staticmethod
    def __get_title(soup) -> (str, str):
        assert isinstance(soup, bs4.BeautifulSoup)

        title = soup.find('title')
        tokens = title.split(':')
        if len(tokens) == 2:
            return tuple(map(lambda x: x.split(), tokens))

        subtitle = soup.find('meta', {'property': 'og:title'})
        if subtitle is not None:
            return subtitle.string

        title = title.string
        subtitle = soup.find('div', {'class': 'post_title_area'})

        regex = '[^\n^\r]*'
        for r in re.finditer(regex, subtitle.text):
            subtitle = r.group()
            if subtitle:
                return title, subtitle

        raise RuntimeError

    @staticmethod
    def __get_html_type(url) -> HtmlType:
        assert isinstance(url, str)

        result = re.search('\/category\/', url)
        if result is not None:
            return HtmlType.CATEGORY

        return HtmlType.POST

    @staticmethod
    def __get_base_url(url) -> str:
        assert isinstance(url, str)

        it = re.finditer('([.][\w]+)', url)
        next(it)
        v = next(it)
        return url[:v.end()]

    @staticmethod
    def __get_file_path(save_path, blog_title, category, post_title):
        paths = [blog_title, category, post_title]
        for i, path in enumerate(paths):
            path = re.sub(r'[^\w\-_ ]', '', path)
            path = path.strip()
            paths[i] = path

        return os.path.join(save_path, *paths)

# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    #url = r'http://ehei.egloos.com/7529993'
    #url = r'http://darkelfy.egloos.com/2199556'
    url = r'http://swanjun.egloos.com/category/%EB%A7%8C%ED%99%94%EB%A6%AC%EB%B7%B0%2F%EA%B0%90%EC%83%81%2F%EC%A0%95%EB%B3%B4%2F%EC%9E%A1%EC%8D%B0'
    ##url = r'http://sg-mh.com/2018413'

    save_path = r'C:\Users\ehei2\Downloads'
    crawler = Crawler(url, save_path)
