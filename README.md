# Simple-HF-Model-Downloader
Extremely simple python program to download models from Huggingface

Exactly what it says on the tin.  Supply the HF model name and a local directory, and a new directory with the model's name will be created in the 
location specified. All the pieces-parts of the raw model will be downloaded there.  Very useful if you're savvy enough to mess around 
with quantizing and merging models, but not enough to want to mess with git.

Both a CLI and GUI version are provided.

For the CLI version, the command format is 
````
python hfdl.py <HF model name> <Local download location>
````


For the GUI version, it's pretty self explanatory.

![hfdl](https://github.com/candre23/Simple-HF-Model-Downloader/assets/36796363/53a74586-62f3-4e92-8c86-d1d63778c696)


Full disclosure:  I do not know python.  This was programmed by AI (Command R+) at my direction.  The process was more arduous than you probably think, 
requiring a few hours and several dozen revisions.  But it got there in the end. Since "I" did not write it, I am releasing it into the public domain.
