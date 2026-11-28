export * from "./hwb.js";
import type { Plugin } from "../extend.js";
/**
 * A plugin adding support for HWB (Hue-Whiteness-Blackness) color model.
 * https://en.wikipedia.org/wiki/HWB_color_model
 * https://www.w3.org/TR/css-color-4/#the-hwb-notation
 */
declare const hwbPlugin: Plugin;
export default hwbPlugin;
