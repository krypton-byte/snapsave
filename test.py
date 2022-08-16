import asyncio
from io import BytesIO
from snapsave import Fb
from snapsave import DownloadCallback
import httpx

class Download(DownloadCallback):
    def __init__(self, length: int) -> None:
        super().__init__()
        self.io = BytesIO()
        self.length = length
        self.clength = 0
    async def on_open(self, client: httpx.AsyncClient, response: httpx.Response):
        print('Starting Download', end='\r')
    async def on_progress(self, binaries: bytes):
        self.io.write(binaries)
        self.clength += binaries.__len__()
        print(f'Download: %s          ' % ((int(self.clength/self.length * 100)).__str__() + '%'), end='\r')
    async def on_finish(self, client: httpx.AsyncClient, response: httpx.Response):
        self.io.seek(0)
async def main(url):
    vid = await Fb().from_url(url)
    print(vid)
    dd = Download(await vid[1].get_size())
    await vid[1].download(dd)
    open('video.mp4','wb').write(dd.io.getvalue())
asyncio.run(main(url)) #type: ignore