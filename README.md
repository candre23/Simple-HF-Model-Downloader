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

![hfdl](https://github.com/user-attachments/assets/bd747082-b027-4c78-bf23-0b3f33f76458)

Full disclosure:  I do not know python.  This is low-effort vibeslop.
