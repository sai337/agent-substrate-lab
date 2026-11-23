# Static Go binary on a distroless base: no shell, no package manager, nothing
# for a hijacked agent to live off. Pin the base images by digest in your registry.
FROM --platform=$BUILDPLATFORM golang:1.23 AS build
ARG TARGETOS=linux TARGETARCH=amd64
WORKDIR /src
COPY go.mod main.go ./
RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH go build -trimpath -ldflags="-s -w" -o /memory-agent .

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /memory-agent /memory-agent
USER 65532:65532
ENTRYPOINT ["/memory-agent"]
