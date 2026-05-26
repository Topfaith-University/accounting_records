import { Routes } from '@angular/router';
import { authGuard } from './auth/guards/auth.guard';

export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () => import('./auth/login/login.component').then(m => m.LoginComponent)
  },
  {
    path: '',
    loadComponent: () => import('./shell/shell.component').then(m => m.ShellComponent),
    canActivate: [authGuard],
    children: [
      { path: '', redirectTo: 'accounts', pathMatch: 'full' },
      {
        path: 'accounts',
        loadComponent: () => import('./accounts/account-list/account-list.component').then(m => m.AccountListComponent)
      },
      {
        path: 'journals',
        loadComponent: () => import('./journals/entry-list/entry-list.component').then(m => m.EntryListComponent)
      },
      {
        path: 'journals/new',
        loadComponent: () => import('./journals/entry-form/entry-form.component').then(m => m.EntryFormComponent)
      },
      {
        path: 'journals/:id',
        loadComponent: () => import('./journals/entry-detail/entry-detail.component').then(m => m.EntryDetailComponent)
      },
    ]
  },
  { path: '**', redirectTo: 'accounts' }
];
