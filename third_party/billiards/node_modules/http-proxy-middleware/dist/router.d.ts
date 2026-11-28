import type * as http from 'node:http';
import type { ProxyTarget } from 'httpxy';
import type { Options } from './index.js';
export declare function getTarget<TReq extends http.IncomingMessage = http.IncomingMessage, TRes extends http.ServerResponse = http.ServerResponse>(req: TReq, res: TRes | undefined, config: Options<TReq, TRes>): Promise<ProxyTarget | undefined>;
