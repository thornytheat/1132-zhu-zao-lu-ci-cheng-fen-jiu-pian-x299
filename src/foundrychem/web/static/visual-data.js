function svgNode(tag, attributes, label) {
    const element = document.createElementNS('http://www.w3.org/2000/svg', tag);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
    if (label !== undefined) element.textContent = text(label);
    return element;
}

function figure(target, width, height) {
    const svg = svgNode('svg', {viewBox:`0 0 ${width} ${height}`, role:'img', 'aria-label':target.dataset.axis});
    target.append(svg);
    return svg;
}

function drawProjectChart(target, points) {
    const board = figure(target, 640, 247);
    const low = Math.min(0,...points.map(i=>i.value));
    const high = Math.max(1,...points.map(i=>i.value));
    const origin = 40 + (0-low)/(high-low)*550;
    board.append(svgNode('line',{x1:origin,x2:origin,y1:15,y2:225,class:'chart-grid'}));
    points.forEach((point,i)=> {
        const x = 40+(point.value-low)/(high-low)*550;
        const y = 24+i*188/Math.max(points.length-1,1);
        board.append(svgNode('line',{x1:origin,x2:x,y1:y,y2:y,class:'series-line'}));
        const dot = svgNode('circle',{cx:x,cy:y,r:5,class:'chart-dot'});
        dot.append(svgNode('title',{},`${point.label} ${text(point.value)}`));
        board.append(dot);
        if(i%2===0) board.append(svgNode('text',{x:Math.min(x+9,590),y:y+4,class:'chart-caption'},point.label.slice(0,9)));
    });
}
