import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { request } from '@/api/client'
import type {
  Project,
  ProjectCreate,
  ProjectDetail,
  ProjectSource,
  ProjectUpdate,
} from '@/features/projects/types'

const listKey = ['projects'] as const
const detailKey = (id: string) => ['projects', id] as const

export function useProjects() {
  return useQuery({
    queryKey: listKey,
    queryFn: () => request<Project[]>('/projects'),
  })
}

export function useProject(id: string) {
  return useQuery({
    queryKey: detailKey(id),
    queryFn: () => request<ProjectDetail>(`/projects/${id}`),
  })
}

export function useCreateProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ProjectCreate) =>
      request<ProjectDetail>('/projects', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: listKey }),
  })
}

export function useUpdateProject(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ProjectUpdate) =>
      request<ProjectDetail>(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    onSuccess: (project) => {
      queryClient.setQueryData(detailKey(id), project)
      void queryClient.invalidateQueries({ queryKey: listKey })
    },
  })
}

export function useDeleteProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => request<void>(`/projects/${id}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: listKey }),
  })
}

export function useAddTextSource(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { kind: 'topic' | 'text'; content: string }) =>
      request<ProjectSource>(`/projects/${projectId}/sources`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: detailKey(projectId) }),
  })
}

export function useUploadSource(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return request<ProjectSource>(`/projects/${projectId}/sources/upload`, {
        method: 'POST',
        body: form,
      })
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: detailKey(projectId) }),
  })
}

export function useDeleteSource(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (sourceId: string) =>
      request<void>(`/projects/${projectId}/sources/${sourceId}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: detailKey(projectId) }),
  })
}
