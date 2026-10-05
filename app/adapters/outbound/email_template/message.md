---
kind: "{{ kind }}"
language: "{{ language }}"
subject: "{{ subject }}"
preheader: "{{ preheader }}"
eyebrow: "{{ eyebrow }}"
---

# {{ title }}

<!-- if:first_name -->
Hola {{ first_name }},
<!-- endif -->
<!-- unless:first_name -->
Hola,
<!-- endunless -->

{{ intro }}

<!-- if:highlight_value -->
> [!HIGHLIGHT] {{ highlight_label }} | {{ highlight_value }}
<!-- endif -->

<!-- if:items_title -->
## {{ items_title }}
<!-- endif -->

<!-- if:items -->
{{ items }}
<!-- endif -->

<!-- if:table -->
{{ table }}
<!-- endif -->

<!-- if:notice -->
> [!NOTICE] {{ notice }}
<!-- endif -->

<!-- if:button_url -->
> [!BUTTON] {{ button_label }} | {{ button_url }}
<!-- endif -->

<!-- if:closing -->
{{ closing }}
<!-- endif -->
