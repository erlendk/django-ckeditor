from django.conf.urls.defaults import patterns, url

urlpatterns = patterns('',
    url(r'^upload/', 'ckeditor.views.upload', name='ckeditor_upload'),
    url(r'^fb_upload/', 'ckeditor.views.fb_upload', name='ckeditor_fb_upload'),
    url(r'^browse/', 'ckeditor.views.browse', name='ckeditor_browse'),
)
