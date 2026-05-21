// api/request.ts
import { apiClient } from './client';
import { ApiEndpoint } from './endpoints';

type Primitive = string | number | boolean | null | undefined;
type RequestParams = Record<string, Primitive>;
type PathParams = string | number | RequestParams;

type RequestOptions<TReq> = {
    data?: TReq | FormData;
    params?: RequestParams;
    pathParams?: PathParams;
    headers?: Record<string, string>;
};

export async function request<TReq, TRes>(
    endpoint: ApiEndpoint<TReq, TRes>,
    options?: RequestOptions<TReq>
): Promise<TRes> {
    const url =
        typeof endpoint.url === 'function'
            ? endpoint.url(options?.pathParams)
            : endpoint.url;

    const isFormData = options?.data instanceof FormData;
    const headers = isFormData
        ? { ...(options?.headers || {}) }
        : { 'Content-Type': 'application/json', ...(options?.headers || {}) };

    const response = await apiClient({
        method: endpoint.method,
        url,
        data: options?.data,
        params: options?.params,
        headers,
    });

    return response.data;
}
