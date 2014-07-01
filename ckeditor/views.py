from datetime import datetime
import os

from django.conf import settings
from django.core.files.storage import default_storage
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.shortcuts import render_to_response
from django.template import RequestContext

from ckeditor import image_processing
from ckeditor import utils


def get_upload_filename(upload_name, user):
    # If CKEDITOR_RESTRICT_BY_USER is True upload file to user specific path.
    if getattr(settings, 'CKEDITOR_RESTRICT_BY_USER', False):
        user_path = user.username
    else:
        user_path = ''

    # Generate date based path to put uploaded file.
    date_path = datetime.now().strftime('%Y/%m/%d')

    # Complete upload path (upload_path + date_path).
    upload_path = os.path.join(
        settings.CKEDITOR_UPLOAD_PATH, user_path, date_path)

    if getattr(settings, "CKEDITOR_UPLOAD_SLUGIFY_FILENAME", True):
        upload_name = utils.slugify_filename(upload_name)

    return default_storage.get_available_name(os.path.join(upload_path, upload_name))


@csrf_exempt
def upload(request):
    """
    Uploads a file and send back its URL to CKEditor.

    TODO:
        Validate uploads
    """
    # Get the uploaded file from request.
    upload = request.FILES['upload']

    #Verify that file is a valid image
    backend = image_processing.get_backend()
    try:
        backend.image_verify(upload)
    except IOError:
        return HttpResponse("""
                   <script type='text/javascript'>
                        alert('Invalid image')
                        window.parent.CKEDITOR.tools.callFunction({0});
                   </script>""".format(request.GET['CKEditorFuncNum']))

    # Open output file in which to store upload.
    upload_filename = get_upload_filename(upload.name, request.user)
    saved_path = default_storage.save(upload_filename, upload)

    if backend.should_create_thumbnail(saved_path):
        backend.create_thumbnail(saved_path)

    url = utils.get_media_url(saved_path)

    # Respond with Javascript sending ckeditor upload url.
    return HttpResponse("""
    <script type='text/javascript'>
        window.parent.CKEDITOR.tools.callFunction({0}, '{1}');
    </script>""".format(request.GET['CKEditorFuncNum'], url))


def get_image_files(user=None, path=''):
    """
    Recursively walks all dirs under upload dir and generates a list of
    full paths for each file found.
    """
    # If a user is provided and CKEDITOR_RESTRICT_BY_USER is True,
    # limit images to user specific path, but not for superusers.
    STORAGE_DIRECTORIES = 0
    STORAGE_FILES = 1

    restrict = getattr(settings, 'CKEDITOR_RESTRICT_BY_USER', False)
    if user and not user.is_superuser and restrict:
        user_path = user.username
    else:
        user_path = ''

    browse_path = os.path.join(settings.CKEDITOR_UPLOAD_PATH, user_path, path)

    try:
        storage_list = default_storage.listdir(browse_path)
    except NotImplementedError:
        return
    except OSError:
        return

    for filename in storage_list[STORAGE_FILES]:
        if os.path.splitext(filename)[0].endswith('_thumb'):
            continue
        filename = os.path.join(browse_path, filename)
        yield filename

    for directory in storage_list[STORAGE_DIRECTORIES]:
        directory_path = os.path.join(path, directory)
        for element in get_image_files(user=user, path=directory_path):
            yield element


def get_files_browse_urls(user=None):
    """
    Recursively walks all dirs under upload dir and generates a list of
    thumbnail and full image URL's for each file found.
    """
    files = []
    for filename in get_image_files(user=user):
        src = utils.get_media_url(filename)
        if getattr(settings, 'CKEDITOR_IMAGE_BACKEND', None):
            thumb = utils.get_media_url(utils.get_thumb_filename(filename))
        else:
            thumb = src
        files.append({
            'thumb': thumb,
            'src': src,
            'is_image': is_image(src)
        })

    return files


def is_image(path):
    ext = path.split('.')[-1].lower()
    return ext in ['jpg', 'jpeg', 'png', 'gif']


def browse(request):
    context = RequestContext(request, {
        'files': get_files_browse_urls(request.user),
    })
    return render_to_response('browse.html', context)


@csrf_exempt
def fb_upload(request):
    """
    The idea and a lot of code stolen from The Atlantic
    https://github.com/theatlantic/django-ckeditor/blob/atl/4.1.x/ckeditor/views.py

    A wrapper around django-filebrowser's file upload view. It returns a
    javascript function call to CKEDITOR.tools.callFunction(), which
    CKEDITOR expects.
    """
    # Set the upload folder, if not declared otherwise
    if not request.GET.get('folder'):
        from django.utils.timezone import now
        request.GET = request.GET.copy()
        request.GET['folder'] = now().strftime('%Y/%m/%d')

    try:
        from filebrowser.sites import site
    except ImportError:
        raise Exception(
                "django-filebrowser must be installed and be of version 3.5.3 or greater; "
                "currently at version %s" % filebrowser.VERSION)
    upload_file_view = site._upload_file

    # Connect to django-filebrowser's filebrowser_post_upload signal.
    # This is the only way to get the uploaded file's location into ckeditor.views.fb_upload 
    # when wrapping a call to the filebrowser's file upload view function.
    try:
        # django-filebrowser >= 3.5.0
        from filebrowser.signals import filebrowser_post_upload
    except ImportError:
        raise Exception(
                "django-filebrowser must be installed and be of version 3.5.3 or greater; "
                "currently at version %s" % filebrowser.VERSION)
    
    request.fb_upload_file = None

    def post_upload_callback(sender, **kwargs):
        # sender will be the request passed to upload_file_view
        sender.fb_upload_file = kwargs.get('file')
    filebrowser_post_upload.connect(post_upload_callback, dispatch_uid='django_ckeditor__fb_upload__filebrowser_post_upload')

    # Call original view function.
    # Within this function, the filebrowser_post_upload signal will be sent,
    # and our signal receiver will add the filebrowser.base.FileObject instance to request.fb_upload_file.
    upload_file_view(request)

    # clean up signal connection
    filebrowser_post_upload.disconnect(post_upload_callback, dispatch_uid='django_ckeditor__fb_upload__filebrowser_post_upload')
    
    if not request.fb_upload_file:
        return HttpResponse("Error uploading file")
    
    return HttpResponse("""
    <script type='text/javascript'>
    window.parent.CKEDITOR.tools.callFunction(%s, '%s');
    </script>""" % (request.GET['CKEditorFuncNum'], request.fb_upload_file.url))
