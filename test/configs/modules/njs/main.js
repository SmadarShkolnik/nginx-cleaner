function hello(r) {
    r.headersOut['Content-Type'] = 'text/plain';
    r.return(200, `njs ${njs.version} method=${r.method} x=${r.args.x || ''}\n`);
}

export default { hello };
