from __future__ import annotations
from asyncio.tasks import ensure_future, gather
from io import BufferedWriter, BytesIO
from ast import literal_eval
from typing import Any, Generator, Literal, Optional, Union
import httpx
from httpx import AsyncClient
from .decoder import decoder
import re
from enum import Enum


def translate(text: str) -> bool:
    return text.lower() in ['iya', 'yes']


class Regex:
    URL_FILTER = re.compile(r'(https?://[\w+&=\.%\-_/?;]+)')
    ORIGIN_URL = re.compile(r'https?://[\w\.-]+/')
    RESOLUTION = re.compile(r'>(\w+)p')
    TABLE = re.compile(r'\<table.*\<\/table\>', re.DOTALL)
    RENDER = re.compile(r'Tidak|Iya|No|Yes')
    FROM_SNAPAPP = re.compile(r'^https?://snapsave\.app')
    QUALITY = re.compile(r'"video-quality">(\d+|Audio|HD|SD)')
    DECODER_ARGS = re.compile(r'\(\".*?,.*?,.*?,.*?,.*?.*?\)')
    COVER = re.compile(r'<img src=[\\]?"([\w://\.\=&?-]+)')


def sorted_video(videos: list[FacebookVideo]) -> list[FacebookVideo]:
    data = []
    data1 = []
    for v in filter(lambda x: not x.render, videos):
        data.append(v)
    for v in filter(lambda x: x.render, videos):
        data1.append(v)
    return [*sorted(data, reverse=True), *sorted(data1, reverse=True)]


class DownloadCallback:
    def __init__(self) -> None:
        self.finished = False

    async def on_open(
        self,
        client: httpx.AsyncClient,
        response: httpx.Response
    ):
        raise NotImplementedError()

    async def on_progress(self, binaries: bytes):
        raise NotImplementedError()

    async def on_finish(
        self,
        client: httpx.AsyncClient,
        response: httpx.Response
    ):
        raise NotImplementedError()


class Type(Enum):
    AUDIO = 0
    VIDEO = 1


class Quality(Enum):
    _1080P = 1080
    _840P = 840
    _720P = 720
    _640P = 640
    _540P = 540
    _480P = 480
    _360P = 360
    _270P = 270
    _240P = 240
    _180P = 180
    AUDIO = 'AUDIO'

    @classmethod
    def from_res(
        cls,
        res: Union[Literal['HD', 'SD', 'AUDIO'], int]
    ) -> Quality:
        if res == 'HD':
            return cls._720P
        elif res == 'SD':
            return cls._640P
        elif res == 'AUDIO':
            return cls.AUDIO
        for i in filter(lambda x: x.value == res, cls.__members__.values()):
            return i
        raise KeyError

    @property
    def type(self) -> Type:
        return Type.AUDIO if isinstance(self.value, str) else Type.VIDEO

    def __gt__(self, comp: Quality) -> Quality:
        return self.value > comp.value


class FacebookVideo(AsyncClient):
    def __init__(
        self,
        url: str,
        quality: Quality,
        render: Union[bool, Literal['HD', 'SD', 'AUDIO']],
        file_size: Optional[int] = None
    ):
        super().__init__()
        self.url_v = url
        self.quality = quality
        self.render = render in ['HD', 'SD', 'AUDIO'] or render
        self.file_size = file_size

    def __gt__(self, comp: FacebookVideo) -> bool:
        return self.quality != Quality.AUDIO and (
            self.quality > comp.quality) and not self.render

    @property
    def is_sd(self) -> bool:
        return self.quality == Quality._360P and not self.render

    @property
    def is_hd(self) -> bool:
        return self.quality == Quality._720P and not self.render

    @property
    def is_audio(self) -> bool:
        return self.quality == Quality.AUDIO

    async def get_size(self) -> int:
        return self.file_size or int((
            await self.stream(
                'GET',
                self.url_v
            ).__aenter__()
        ).headers.get("Content-Length", 0))

    async def download(
        self,
        out: Union[BufferedWriter, BytesIO, DownloadCallback],
        chunk_size: int = int(1024*0.5)
    ) -> None:
        async with self.stream('GET', self.url_v) as request:
            if isinstance(out, DownloadCallback):
                tasks = []
                await out.on_open(self, request)
                async for i in request.aiter_bytes(chunk_size):
                    tasks.append(ensure_future(out.on_progress(i)))
                await gather(*tasks)
                await out.on_finish(self, request)
            else:
                async for i in request.aiter_bytes(chunk_size):
                    out.write(i)

    def __repr__(self) -> str:
        return f'{self.quality.value}::render={self.render}' + ('::'+[
            'SD', 'HD'][self.is_hd] if self.is_hd or self.is_sd else '')


class Videos(list):

    def __init__(self, cover: str):
        super().__init__()
        self.cover = cover

    def __getitem__(self, i) -> FacebookVideo:
        return super().__getitem__(i)

    def __iter__(self) -> Generator[FacebookVideo, None, None]:
        yield from super().__iter__()


class Fb(AsyncClient):

    def __init__(self):
        super().__init__(timeout=20, follow_redirects=True)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 11.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/101.0.4994.167 Safari/537.36'
        }

    async def from_url(self, url: str) -> Videos:
        await self.get('https://snapsave.app/id')
        resp = await self.post(
            'https://snapsave.app/action.php?lang=id',
            data={'url': url},
            headers={
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': "Linux",
                'sec-fetch-dest': 'iframe',
                'sec-fetch-mode': 'navigate',
                'sec-fetch-site': 'same-origin',
                'origin': 'https://snapsave.app',
                'referer': 'https://snapsave.app/id',
                **self.headers
            }
        )
        dec = decoder(*literal_eval(
            Regex.DECODER_ARGS.findall(resp.text)[0]
        ))
        return await self.extract_content(dec)

    async def extract_content(self, src: str) -> Videos:
        data = []
        n = Regex.TABLE.findall(src)[0].replace('\\"', '"')
        for url, res, render in zip(
            Regex.URL_FILTER.findall(n),
            [int(i) if i.isnumeric() else i.upper(
            ) for i in Regex.QUALITY.findall(n)],
            Regex.RENDER.findall(n)
        ):  # type: ignore
            fsize = None
            if Regex.FROM_SNAPAPP.match(url):
                resp: dict[str, Any] = (await self.get(url)).json()['data']
                url: str = resp['file_path']
                fsize: Union[None, int] = resp.get('file_size')
            data.append(FacebookVideo(
                url,
                Quality.from_res(res),
                translate(render),
                fsize
            ))
        data2 = Videos(Regex.COVER.findall(src)[0])
        data2.extend(sorted_video(data))
        return data2

    async def from_html(self, html: str) -> Videos:
        resp = await self.post(
            'https://snapsave.app/download-private-video',
            data={
                'html_content': html
            },
            headers={
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': "Linux",
                'sec-fetch-dest': 'iframe',
                'sec-fetch-mode': 'navigate',
                'sec-fetch-site': 'same-origin',
                'origin': 'https://snapsave.app',
                **self.headers
            }
        )
        return await self.extract_content(resp.text)
