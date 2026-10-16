# PromaX Automation Suite - imagem Ubuntu com Python + Google Chrome
#
# O chromedriver é instalado AQUI, no build (não deixado para o Selenium
# Manager resolver em runtime) — com a VPN corporativa em full-tunnel,
# qualquer chamada de rede não relacionada ao ProMAX (como o Selenium
# Manager batendo em googlechromelabs.github.io a cada execução) também
# passa pelo túnel e pode dar timeout. Fixar o driver no build elimina essa
# dependência de rede em runtime por completo, independente da VPN.
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HEADLESS=True \
    CHROMEDRIVER_PATH=/usr/local/bin/chromedriver

WORKDIR /app

# Python + dependências de sistema necessárias para o Chrome headless
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        wget \
        gnupg \
        ca-certificates \
        fonts-liberation \
        libnss3 \
        libxss1 \
        libasound2 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libcups2 \
        libdrm2 \
        libgbm1 \
        libgtk-3-0 \
        libnspr4 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxkbcommon0 \
        libxrandr2 \
        xdg-utils \
        unzip \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub \
        | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
        > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y --no-install-recommends google-chrome-stable \
    && rm -rf /var/lib/apt/lists/* \
    && CHROME_VERSION=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+\.\d+') \
    && wget -q -O /tmp/chromedriver.zip "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chromedriver-linux64.zip" \
    && unzip -q /tmp/chromedriver.zip -d /tmp \
    && mv /tmp/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver \
    && chmod +x /usr/local/bin/chromedriver \
    && rm -rf /tmp/chromedriver.zip /tmp/chromedriver-linux64

# Dependências Python (instaladas primeiro para aproveitar cache de camadas)
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Código da aplicação
COPY . .

# data/ e logs/ são montados como volumes (docker-compose.yml) para que o
# SQLite e os arquivos baixados persistam inalterados fora da imagem.
RUN mkdir -p data/arquivos logs

EXPOSE 5000

CMD ["python3", "main.py", "--web"]
