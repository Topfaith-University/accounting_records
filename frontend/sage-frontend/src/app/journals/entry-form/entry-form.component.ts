import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, FormArray, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { JournalsService } from '../../services/journals.service';
import { AccountsService } from '../../services/accounts.service';
import { AuthService } from '../../services/auth.service';
import { AccountSelectComponent } from '../../shared/account-select/account-select.component';

@Component({
  selector: 'app-entry-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, AccountSelectComponent],
  templateUrl: './entry-form.component.html',
})
export class EntryFormComponent implements OnInit {
  form!: FormGroup;
  allAccounts: any[] = [];
  saving = false;
  posting = false;
  error = '';
  entryId: string | null = null;

  get isManagerOrAdmin(): boolean {
    const user = this.auth.getCurrentUser();
    return user?.roles.some((r: string) => ['Manager', 'Admin'].includes(r)) ?? false;
  }

  get isEditMode(): boolean { return !!this.entryId; }
  get lines(): FormArray { return this.form.get('lines') as FormArray; }

  get totalDebit(): number {
    return this.lines.controls.reduce((sum, l) => sum + (Number(l.value.debit_amount) || 0), 0);
  }

  get totalCredit(): number {
    return this.lines.controls.reduce((sum, l) => sum + (Number(l.value.credit_amount) || 0), 0);
  }

  get isBalanced(): boolean {
    return this.lines.length >= 2 && Math.abs(this.totalDebit - this.totalCredit) < 0.005;
  }

  constructor(
    private fb: FormBuilder,
    private journalsService: JournalsService,
    private accountsService: AccountsService,
    private auth: AuthService,
    private route: ActivatedRoute,
    private router: Router,
  ) {}

  async ngOnInit() {
    this.form = this.fb.group({
      date: [new Date().toISOString().slice(0, 10), Validators.required],
      description: ['', Validators.required],
      entry_type: ['MANUAL'],
      lines: this.fb.array([]),
    });
    try {
      const data = await this.accountsService.getAll();
      this.allAccounts = data.results ?? data;
      this.entryId = this.route.snapshot.paramMap.get('id');
      if (this.entryId) {
        const entry = await this.journalsService.getEntry(this.entryId);
        this.form.patchValue({
          date: entry.date ?? '',
          description: entry.description ?? '',
          entry_type: entry.entry_type ?? 'MANUAL',
        });
        this.lines.clear();
        for (const line of (entry.lines ?? [])) {
          this.lines.push(this.fb.group({
            account_id: [line.account_id ?? '', Validators.required],
            debit_amount: [line.side === 'DEBIT' ? line.amount : null],
            credit_amount: [line.side === 'CREDIT' ? line.amount : null],
            description: [line.description ?? ''],
          }));
        }
      }
      if (this.lines.length === 0) {
        this.addLine('DEBIT');
        this.addLine('CREDIT');
      }
    } catch {
      this.error = 'Failed to load journal entry form. Please refresh.';
    }
  }

  addLine(side: 'DEBIT' | 'CREDIT' = 'DEBIT') {
    this.lines.push(this.fb.group({
      account_id: ['', Validators.required],
      debit_amount: [null],
      credit_amount: [null],
      description: [''],
    }));
  }

  removeLine(i: number) {
    if (this.lines.length > 2) this.lines.removeAt(i);
  }

  private buildPayload() {
    const val = this.form.value;
    return {
      date: val.date,
      description: val.description,
      entry_type: val.entry_type,
      lines: val.lines
        .filter((l: any) => Number(l.debit_amount) > 0 || Number(l.credit_amount) > 0)
        .map((l: any) => ({
          account_id: l.account_id,
          side: Number(l.debit_amount) > 0 ? 'DEBIT' : 'CREDIT',
          amount: Number(l.debit_amount) > 0 ? Number(l.debit_amount) : Number(l.credit_amount),
          description: l.description,
        })),
    };
  }

  async save() {
    if (!this.form.valid || !this.isBalanced) return;
    this.saving = true;
    this.error = '';
    try {
      const entry = this.entryId
        ? await this.journalsService.updateEntry(this.entryId, this.buildPayload())
        : await this.journalsService.createEntry(this.buildPayload());
      this.router.navigate(['/journals', entry.entry_id]);
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Save failed.');
    } finally { this.saving = false; }
  }

  async saveAndPost() {
    if (!this.form.valid || !this.isBalanced) return;
    this.posting = true;
    this.error = '';
    try {
      const entry = this.entryId
        ? await this.journalsService.updateEntry(this.entryId, this.buildPayload())
        : await this.journalsService.createEntry(this.buildPayload());
      await this.journalsService.postEntry(entry.entry_id);
      this.router.navigate(['/journals', entry.entry_id]);
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Post failed.');
    } finally { this.posting = false; }
  }
}
