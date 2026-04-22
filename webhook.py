import requests as http


def disparar_webhook(webhook_url, post, base_url):
    """POST post data to Make.com webhook for Instagram publishing.

    Make.com scenario maps these fields to the Instagram for Business module:
    - imagem_url  → photo URL (must be publicly accessible)
    - legenda     → caption text (includes hashtags)
    - titulo      → used in Make.com scenario logging

    Args:
        webhook_url: Make.com custom webhook URL from clientes.make_webhook_url
        post: Post model instance (must have .cliente relationship loaded)
        base_url: Public root URL of the app, e.g. "https://domain.com/"

    Raises:
        requests.HTTPError: if Make.com returns a non-2xx status
        requests.Timeout: if the request exceeds 30 seconds
    """
    imagem_absoluta = None
    if post.imagem_url:
        imagem_absoluta = base_url.rstrip('/') + post.imagem_url

    payload = {
        'post_id': post.id,
        'titulo': post.titulo,
        'legenda': post.legenda,
        'imagem_url': imagem_absoluta,
        'instagram_handle': post.cliente.instagram_handle,
        'data_publicacao': (
            post.data_publicacao.isoformat() if post.data_publicacao else None
        ),
    }

    resp = http.post(webhook_url, json=payload, timeout=30)
    resp.raise_for_status()
    return resp
