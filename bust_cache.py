import os, glob

for file in glob.glob('frontend/*.html'):
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    content = content.replace('.css"', '.css?v=2"')
    with open(file, 'w', encoding='utf-8') as f:
        f.write(content)

print("done")
