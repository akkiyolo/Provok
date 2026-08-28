import os

def update_file(path, replacements):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    for old, new in replacements:
        content = content.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

# global.css
update_file('frontend/css/global.css', [
    ('color:white', 'color:var(--paper)') # For .toast
])
# Need to put white back for btn-red? Wait, replacing color:white with color:var(--paper) will change .btn-red to use var(--paper) instead of white!
# var(--paper) is #f3f0e9 in light mode (almost white) and #11110f in dark mode (almost black). 
# If .btn-red has var(--paper), it will have black text on red button in dark mode! That's bad contrast!
# Let's fix btn-red back to white in global.css!

with open('frontend/css/global.css', 'r', encoding='utf-8') as f: c = f.read()
c = c.replace('.btn-red{background:var(--red);color:var(--paper);border-color:var(--red)}', '.btn-red{background:var(--red);color:white;border-color:var(--red)}')
with open('frontend/css/global.css', 'w', encoding='utf-8') as f: f.write(c)

# components.css
update_file('frontend/css/components.css', [
    ('background:#fff4f1', 'background:var(--paper-2)'),
    ('background:white', 'background:var(--white)')
])

# debate.css
update_file('frontend/css/debate.css', [
    ('color:white', 'color:var(--ink)')
])

# profile.css
update_file('frontend/css/profile.css', [
    ('color:white', 'color:var(--paper)')
])
