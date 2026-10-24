import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, RenderOptions } from "@testing-library/react";

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

export function renderWithClient(ui: React.ReactElement, client = createTestQueryClient(), options?: RenderOptions) {
  return {
    ...render(
      <QueryClientProvider client={client}>
        {ui}
      </QueryClientProvider>,
      options
    ),
    queryClient: client,
  };
}
