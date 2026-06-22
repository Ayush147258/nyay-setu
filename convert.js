const fs = require('fs');
const path = require('path');

function convertHtmlToJsx(html) {
  // Convert class to className
  let jsx = html.replace(/class=/g, 'className=');
  // Convert style attributes to objects (naive, might need manual touchup but let's try)
  // For style="width:13px;height:13px", we can just replace with style={{width: '13px', height: '13px'}}
  jsx = jsx.replace(/style="([^"]*)"/g, (match, p1) => {
    const parts = p1.split(';').filter(p => p.trim());
    const styleObj = {};
    parts.forEach(p => {
      const [key, val] = p.split(':');
      if (key && val) {
        const camelKey = key.trim().replace(/-([a-z])/g, g => g[1].toUpperCase());
        styleObj[camelKey] = val.trim();
      }
    });
    return `style={${JSON.stringify(styleObj)}}`;
  });
  // Convert svg attributes
  const svgAttrs = ['stroke-width', 'stroke-linecap', 'stroke-dasharray', 'fill-rule', 'clip-path', 'stroke-linejoin', 'text-anchor', 'font-family', 'font-size', 'mix-blend-mode'];
  svgAttrs.forEach(attr => {
    const camel = attr.replace(/-([a-z])/g, g => g[1].toUpperCase());
    const regex = new RegExp(attr + '=', 'g');
    jsx = jsx.replace(regex, camel + '=');
  });

  // Self closing tags
  const voidElements = ['img', 'br', 'hr', 'input', 'meta', 'link'];
  voidElements.forEach(tag => {
    const regex = new RegExp(`<${tag}([^>]*[^/])>`, 'gi');
    jsx = jsx.replace(regex, `<${tag}$1 />`);
  });
  
  // Also clean up any unclosed br/hr
  jsx = jsx.replace(/<br>/g, '<br />');
  jsx = jsx.replace(/<hr>/g, '<hr />');

  // Replace <!-- ... --> with {/* ... */}
  jsx = jsx.replace(/<!--(.*?)-->/gs, '{/* $1 */}');

  return jsx;
}

function processFile(name) {
  const content = fs.readFileSync(name, 'utf8');
  
  // Extract style
  const styleMatch = content.match(/<style>([\s\S]*?)<\/style>/);
  const styleContent = styleMatch ? styleMatch[1] : '';
  
  // Extract body
  const bodyMatch = content.match(/<body>([\s\S]*?)<\/body>/);
  let bodyContent = bodyMatch ? bodyMatch[1] : content;
  
  // Remove script tag from body if present
  const scriptMatch = bodyContent.match(/<script>([\s\S]*?)<\/script>/);
  if (scriptMatch) {
    bodyContent = bodyContent.replace(scriptMatch[0], '');
  }

  // Convert to JSX
  let jsxContent = convertHtmlToJsx(bodyContent.trim());
  
  return { styleContent, jsxContent, scriptContent: scriptMatch ? scriptMatch[1] : '' };
}

const landing = processFile('landing.html');
fs.writeFileSync('landing_extracted.json', JSON.stringify(landing));

const dashboard = processFile('dashboard.html');
fs.writeFileSync('dashboard_extracted.json', JSON.stringify(dashboard));

console.log('Done');
