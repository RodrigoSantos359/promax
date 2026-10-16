"""
Proxy TCP (passthrough, sem terminar TLS) que repassa conexões de uma porta
local para o endpoint real da API WKRADAR (172.20.5.8:443).

Roda FORA do Docker, direto no WSL2 — ver docstring de
`src/integrations/wkradar_client.py` e `scripts/wkradar-proxy/setup.ps1` para
o motivo (containers Docker, neste ambiente Docker Desktop/Windows, não
conseguem rotear até essa rede interna; a distro WSL2 consegue).
"""

import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("wkradar_proxy")

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 18443
DEST_HOST = "172.20.5.8"
DEST_PORT = 443


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        writer.close()


async def handle_client(client_reader, client_writer):
    peer = client_writer.get_extra_info("peername")
    try:
        dest_reader, dest_writer = await asyncio.open_connection(DEST_HOST, DEST_PORT)
    except Exception as e:
        logger.error(f"Falha ao conectar em {DEST_HOST}:{DEST_PORT} para cliente {peer}: {e}")
        client_writer.close()
        return

    logger.info(f"Conexão aberta: {peer} -> {DEST_HOST}:{DEST_PORT}")
    await asyncio.gather(
        pipe(client_reader, dest_writer),
        pipe(dest_reader, client_writer),
    )
    logger.info(f"Conexão encerrada: {peer}")


async def main():
    server = await asyncio.start_server(handle_client, LISTEN_HOST, LISTEN_PORT)
    logger.info(f"Proxy TCP escutando em {LISTEN_HOST}:{LISTEN_PORT} -> {DEST_HOST}:{DEST_PORT}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
