import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, FormArray, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { JournalsService } from '../../services/journals.service';
import { AccountsService } from '../../services/accounts.service';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-entry-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './entry-form.component.html',
})
export class EntryFormComponent implements OnInit {
  form!: FormGroup;
  accounts: any[] = [];
  saving = false;
  posting = false;
  error = '';

  get isManagerOrAdmin(): boolean {
    const user = this.auth.getCurrentUser();
    return user?.roles.some((r: string) => ['Manager', 'Admin'].includes(r)) ?? false;
  }

  get lines(): FormArray { return this.form.get('lines') as FormArray; }

  get totalDebit(): number {
    return this.lines.controls
      .filter(l => l.value.side === 'DEBIT')
      .reduce((sum, l) => sum + (Number(l.value.amount) || 0), 0);
  }

  get totalCredit(): number {
    return this.lines.controls
      .filter(l => l.value.side === 'CREDIT')
      .reduce((sum, l) => sum + (Number(l.value.amount) || 0), 0);
  }

  get isBalanced(): boolean {
    return this.lines.length >= 2 && Math.abs(this.totalDebit - this.totalCredit) < 0.005;
  }

  constructor(
    private fb: FormBuilder,
    private journalsService: JournalsService,
    private accountsService: AccountsService,
    private auth: AuthService,
    private router: Router,
  ) {}

  async ngOnInit() {
    this.form = this.fb.group({
      date: [new Date().toISOString().slice(0, 10), Validators.required],
      description: ['', Validators.required],
      entry_type: ['MANUAL'],
      lines: this.fb.array([]),
    });
    this.addLine('DEBIT');
    this.addLine('CREDIT');
    const data = await this.accountsService.getAll();
    this.accounts = data.results ?? data;
  }

  addLine(side: 'DEBIT' | 'CREDIT' = 'DEBIT') {
    this.lines.push(this.fb.group({
      account_id: ['', Validators.required],
      side: [side, Validators.required],
      amount: [null, [Validators.required, Validators.min(0.01)]],
      description: [''],
    }));
  }

  removeLine(i: number) {
    if (this.lines.length > 2) this.lines.removeAt(i);
  }

  async save() {
    if (!this.form.valid || !this.isBalanced) return;
    this.saving = true;
    this.error = '';
    try {
      const entry = await this.journalsService.createEntry(this.form.value);
      this.router.navigate(['/journals', entry.entry_id]);
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? JSON.stringify(e.response?.data) ?? 'Save failed.';
    } finally { this.saving = false; }
  }

  async saveAndPost() {
    if (!this.form.valid || !this.isBalanced) return;
    this.posting = true;
    this.error = '';
    try {
      const entry = await this.journalsService.createEntry(this.form.value);
      await this.journalsService.postEntry(entry.entry_id);
      this.router.navigate(['/journals', entry.entry_id]);
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? JSON.stringify(e.response?.data) ?? 'Post failed.';
    } finally { this.posting = false; }
  }
}
