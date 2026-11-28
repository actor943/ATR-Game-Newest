export * from "./cmyk.js";
import type { Plugin } from "../extend.js";
/**
 * A plugin adding support for CMYK color space.
 * https://lea.verou.me/2009/03/cmyk-colors-in-css-useful-or-useless/
 * https://en.wikipedia.org/wiki/CMYK_color_model
 */
declare const cmykPlugin: Plugin;
export default cmykPlugin;
