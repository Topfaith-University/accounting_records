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
      {
        path: 'banks',
        loadComponent: () => import('./banks/bank-account-list/bank-account-list.component').then(m => m.BankAccountListComponent)
      },
      {
        path: 'banks/reconciliations/:id',
        loadComponent: () => import('./banks/bank-reconciliation/bank-reconciliation.component').then(m => m.BankReconciliationComponent)
      },
      {
        path: 'banks/:id',
        loadComponent: () => import('./banks/bank-account-detail/bank-account-detail.component').then(m => m.BankAccountDetailComponent)
      },
      {
        path: 'reports/trial-balance',
        loadComponent: () => import('./reports/trial-balance/trial-balance.component').then(m => m.TrialBalanceComponent)
      },
      { path: 'reports/income-statement', loadComponent: () => import('./reports/income-statement/income-statement.component').then(m => m.IncomeStatementComponent) },
      { path: 'reports/balance-sheet', loadComponent: () => import('./reports/balance-sheet/balance-sheet.component').then(m => m.BalanceSheetComponent) },
      { path: 'reports/gl-detail', loadComponent: () => import('./reports/gl-detail/gl-detail.component').then(m => m.GlDetailComponent) },
    ]
  },
  { path: '**', redirectTo: 'accounts' }
];
