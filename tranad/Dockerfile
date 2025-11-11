# Base image: Ubuntu 20.04 + CUDA 11.3
FROM nvidia/cuda:11.3.1-cudnn8-devel-ubuntu20.04

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DEBIAN_FRONTEND=noninteractive

# Install System Deps: Python 3.8, pip, git, libcurl4, and comprehensive fonts
RUN apt-get update && \
    apt-get install -y software-properties-common libcurl4 git fontconfig wget cabextract \
    fonts-freefont-ttf fonts-liberation fonts-dejavu \
    gsfonts gsfonts-x11 fonts-liberation2 && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.8 python3.8-distutils python3-pip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Microsoft Core Fonts (including Times New Roman) manually
RUN echo "ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true" | debconf-set-selections && \
    apt-get update && \
    apt-get install -y ttf-mscorefonts-installer && \
    fc-cache -fv && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Update pip & create symlink
RUN python3.8 -m pip install --upgrade pip
RUN ln -s /usr/bin/python3.8 /usr/bin/python

# Set workdir
WORKDIR /app/tranad-sim

# --- 최종 설치 순서 ---

# 1. PyTorch 1.12.1 GPU (compatible with DGL, no is_causal issue)
RUN python3.8 -m pip install torch==1.12.1+cu113 torchvision==0.13.1+cu113 torchaudio==0.12.1 --extra-index-url https://download.pytorch.org/whl/cu113

# 2. DGL compatible with PyTorch 1.12.1 and CUDA 11.3
RUN python3.8 -m pip install dgl-cu113 -f https://data.dgl.ai/wheels/repo.html

# 3. requirements.txt 복사 및 설치 (dgl이 제거된 버전)
COPY ./tranad-sim/requirements.txt .
RUN python3.8 -m pip install -r requirements.txt

# 4. 기타 빠진 의존성 설치
RUN python3.8 -m pip install pyyaml pydantic

# 5. Manually and recursively copy SciencePlots styles to Matplotlib's style directory
RUN MPLLIBDIR=$(python3.8 -c 'import matplotlib; print(matplotlib.get_configdir())') && \
    mkdir -p $MPLLIBDIR/stylelib && \
    SCLIBDIR=$(python3.8 -c 'import site; print(site.getsitepackages()[0])') && \
    find $SCLIBDIR/scienceplots/styles/ -name "*.mplstyle" -exec cp {} $MPLLIBDIR/stylelib/ \;

# Clear matplotlib font cache and rebuild font list
RUN rm -rf ~/.cache/matplotlib/* /root/.cache/matplotlib/* 2>/dev/null || true && \
    python3.8 -c "import matplotlib; import matplotlib.font_manager as fm; fm._load_fontmanager(try_read_cache=False); print('Font cache rebuilt')"

# Create matplotlibrc to suppress font warnings
RUN mkdir -p /root/.config/matplotlib && \
    echo "font.serif: DejaVu Serif, Liberation Serif, Times New Roman, Times" > /root/.config/matplotlib/matplotlibrc && \
    echo "font.sans-serif: DejaVu Sans, Liberation Sans, Arial" >> /root/.config/matplotlib/matplotlibrc && \
    echo "font.family: sans-serif" >> /root/.config/matplotlib/matplotlibrc

# 6. Copy code
COPY . .