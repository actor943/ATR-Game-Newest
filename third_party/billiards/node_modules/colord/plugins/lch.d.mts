export * from "./lch.js";
import type { Plugin } from "../extend.js";
/**
 * A plugin adding support for CIELCH color space.
 * https://lea.verou.me/2020/04/lch-colors-in-css-what-why-and-how/
 * https://en.wikipedia.org/wiki/CIELAB_color_space#Cylindrical_model
 */
declare const lchPlugin: Plugin;
export default lchPlugin;
