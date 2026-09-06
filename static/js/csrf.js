/**
 * CSRF token for fetch() calls.
 *
 * The server rejects any POST without it, so every JSON request in the game
 * goes through jsonHeaders(). The token comes from the meta tag in base.html.
 */
function csrfToken() {
    const tag = document.querySelector('meta[name="csrf-token"]');
    return tag ? tag.content : '';
}

function jsonHeaders() {
    return {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfToken(),
    };
}
