# keyword finder

## Installation

1. Make sure Python 3.8 or higher and git are installed.

    Windows:

    https://www.python.org/downloads/windows/

    If the installer asks to add Python to the path, check yes.

    https://git-scm.com/download/win

    MacOS:

    Open Terminal. Paste the following commands and press enter.

    ```
    ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
    echo 'export PATH="/usr/local/opt/python/libexec/bin:$PATH"' >> ~/.profile
    brew install python
    ```

    Linux:

    Open a terminal window. Paste the following commands and press enter.

    ```
    sudo apt install -y python3
    sudo apt install -y python3-pip
    sudo apt install -y git
    ```

3. Open a terminal/command prompt window. Run the following command.

    ```
    git clone (repository url)
    ```

4. Run the following commands in the same terminal/command prompt window you just opened. Depending on your system you may need run `pip` instead of `pip3`.

    ```
    cd (repository name)
    pip3 install -r requirements.txt
    ```

## Instructions

1. Put your domains in `user-data/input/input.csv`. The column names must be `Ds Id,Ds Company Website`.
2. Put the keywords to find in `user-data/input/keywords.txt`. One keyword per line.
3. Put the keywords you want to be case sensitive in `user-data/input/keywords-case-sensitive.txt`.
4. Optionally put a list of proxies in `user-data/input/proxies.csv`. The format must be `url,port,username,password`. The proxies are for Google searches only.
5. Run `python3 main.py`. Depending on your system you may need run `python main.py` instead.
6. The output will be in `user-data/input/output.csv`.
7. It will not check the same URL twice. If you want to start over, delete `user-data/database.sqlite`.