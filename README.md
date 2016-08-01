# the-docs

Linux Man Pages

## Setup

### Vagrant

For the local setup to work, you'll need to get [Vagrant](https://www.vagrantup.com/) and [VirtualBox](https://www.virtualbox.org/).

### RE2

You'll need to have [Google's RE2](https://github.com/google/re2) library installed.
For Linux you can follow their installation instructions, but for MacOs, you might prefer to use [Homebrew](http://brew.sh):

    brew install re2
    
### Clone

First step should be to clone this repository:

    git clone https://github.com/davidpoblador/the-docs
    cd the-docs
    
### Prepare Python environment

It is recommended to use [virtualenv](https://virtualenv.pypa.io/en/stable/) or [conda](http://conda.pydata.org/docs/intro.html) for setting up everything within a separate, so your base system is kept untouched. Once in your environment, you can run:

    pip install -r requirements.txt
    
### Get Man Pages
    
Another step should be getting the sources for the man pages. For this task to be easier, the `fetch-man-pages.sh` script is provided:

    cd utils
    ./fetch-manpages-from-packages.py
    
### Create your local virtual machine

Once everything is in place, you can start the local VM:

    vagrant up
    
The first time you do this, it might take quite a few minutes, depending on your setup and Internet connection.
Following executions of this command should be faster, since everything should be in place.
When you finish working with the-docs, you can stop it:

    vagrant halt

### Generate the documents

Now, let's generate documents for the man pages:

    ./main.py dirparse src
    ./main.py generate public_html
