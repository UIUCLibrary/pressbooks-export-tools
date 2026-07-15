# mu-plugins

This directory contains WordPress must-use plugins that wire
`pressbooks-export-tools` into a Pressbooks instance.

## Deployment

Copy `pb-export-postprocess.php` into the `wp-content/mu-plugins/` directory
of the target WordPress install.  Must-use plugins load automatically — no
activation step is required.

```
cp mu-plugins/pb-export-postprocess.php /var/www/html/wp-content/mu-plugins/
```

The plugin also requires a small patch to Pressbooks core so that it calls
the hooks at the right points in the Prince export.  See
[`docs/pressbooks-integration.md`](../docs/pressbooks-integration.md) for the
full setup guide, including the `class-pdf.php` patch and server prerequisites.

## Settings

After the mu-plugin is in place, visit **Dashboard → Settings → PB Export Tools**
to configure the binary paths and enable/disable the pipeline without editing
any PHP.
