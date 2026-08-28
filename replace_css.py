import os

def update_file(path, replacements):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    for old, new in replacements:
        content = content.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

# debate.css
debate_css = 'frontend/css/debate.css'
update_file(debate_css, [
    ('background:var(--ink);color:var(--paper)', ''), # Remove inversion
    ('border-right:1px solid #34322d', 'border-right:1px solid var(--line)'),
    ('background:rgba(17,17,15,.96);border-bottom:1px solid #34322d', 'background:var(--nav-bg);border-bottom:1px solid var(--line)'),
    ('color:#9d988e', 'color:var(--muted)'),
    ('background:#45423b', 'background:var(--paper-3)'),
    ('background:#7d786d', 'background:var(--muted-2)'),
    ('color:#a39e94', 'color:var(--muted)'),
    ('border-bottom:1px solid #34322d', 'border-bottom:1px solid var(--line)'),
    ('color:#8f8a81', 'color:var(--muted-2)'),
    ('color:#ded9d0', 'color:var(--ink)'),
    ('border-left:2px solid #c58a22', 'border-left:2px solid var(--yellow)'),
    ('color:#e3a83d', 'color:var(--yellow)'),
    ('color:#8794ed', 'color:var(--blue)'),
    ('background:#6c675f', 'background:var(--muted)'),
    ('background:#4c9b77', 'background:var(--green)'),
    ('background:#d3a03a', 'background:var(--yellow)'),
    ('border-left:2px solid #4a4740', 'border-left:2px solid var(--line-dark)'),
    ('color:#716d65', 'color:var(--muted-2)'),
    ('border:1px solid #3d3a35', 'border:1px solid var(--line-dark)'),
    ('color:#aaa59c', 'color:var(--muted)'),
    ('border-color:#676158', 'border-color:var(--line)'),
    ('color:#8eaaa2', 'color:var(--green)'),
    ('background:#4ca58b', 'background:var(--green)'),
    ('background:rgba(17,17,15,.97);border-top:1px solid #34322d', 'background:var(--nav-bg);border-top:1px solid var(--line)'),
    ('border:1px solid #46433c', 'border:1px solid var(--line-dark)'),
    ('background:#201f1b', 'background:var(--paper-2)'),
    ('color:#eee9e0', 'color:var(--ink)'),
    ('border-color:#79736a', 'border-color:var(--muted)'),
    ('background:#151411', 'background:var(--paper-2)'),
    ('color:#827d74', 'color:var(--muted)'),
    ('color:#777269', 'color:var(--muted-2)'),
    ('border:1px solid #403d37', 'border:1px solid var(--line)'),
    ('border:1px solid #4b4841', 'border:1px solid var(--line)'),
    ('color:#ddd8cf', 'color:var(--ink)'),
    ('border-color:#8b857b', 'border-color:var(--muted)'),
    ('border-top:1px solid #302e29', 'border-top:1px solid var(--line)')
])

# verdict.css
verdict_css = 'frontend/css/verdict.css'
update_file(verdict_css, [
    ('background:var(--ink);color:var(--paper)', 'background:var(--paper-2);color:var(--ink)'),
    ('color:#817d75', 'color:var(--muted-2)'),
    ('color:#aaa59d', 'color:var(--muted)'),
    ('background:#d8d3ca', 'background:var(--paper-3)'),
    ('background:#bd851f', 'background:var(--yellow)')
])

# feed.css
feed_css = 'frontend/css/feed.css'
update_file(feed_css, [
    ('background:#fffaf7', 'background:var(--paper-2)')
])

# global.css
global_css = 'frontend/css/global.css'
update_file(global_css, [
    ('background:#aaa49a', 'background:var(--muted)'),
    ('background:#292823', 'background:var(--ink-2)'),
    ('border-color:#efb2a9', 'border-color:var(--red)'),
    ('background:#fff4f1', 'background:transparent'),
    ('border-color:#dfc487', 'border-color:var(--yellow)'),
    ('background:#fff9e9', 'background:transparent'),
    ('color:#a26c09', 'color:var(--yellow)'),
    ('border-color:#b9c0ef', 'border-color:var(--blue)'),
    ('background:#f4f5ff', 'background:transparent'),
    ('border-color:#a9cbbd', 'border-color:var(--green)'),
    ('background:#f1f8f4', 'background:transparent')
])

print("done")
